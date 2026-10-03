-- Fit-Reason Agent: views. All arithmetic lives here, never in a model.
-- security_invoker = on so the caller's row-level security applies.

-- ---------- order stages and delay attribution ----------
create or replace view v_order_stages_calc with (security_invoker = on) as
with ev as (
  select order_id,
         min(at) filter (where status = 'stock_available')   as stock_at,
         min(at) filter (where status = 'handed_to_courier') as handed_at,
         min(at) filter (where status = 'delivered')         as delivered_at
  from order_events
  group by order_id
),
vend as (
  select ol.order_id, min(s.vendor_id) as vendor_id
  from order_lines ol join skus s on s.sku_id = ol.sku_id
  group by ol.order_id
),
base as (
  select o.order_id, o.placed_at, o.courier, o.fc, o.pin_zone, o.status, v.vendor_id,
         ev.stock_at, ev.handed_at, ev.delivered_at,
         extract(epoch from (coalesce(ev.stock_at, now()) - o.placed_at)) / 86400.0                     as stock_wait_days,
         case when ev.stock_at is null then null
              else extract(epoch from (coalesce(ev.handed_at, now()) - ev.stock_at)) / 86400.0 end    as fulfilment_days,
         case when ev.handed_at is null then null
              else extract(epoch from (coalesce(ev.delivered_at, now()) - ev.handed_at)) / 86400.0 end as transit_days,
         (select target_days from stage_targets where stage = 'stock_wait') as stock_target,
         (select target_days from stage_targets where stage = 'fulfilment') as fulfilment_target,
         tt.max_days                                                        as transit_target
  from orders o
  join ev on ev.order_id = o.order_id
  join vend v on v.order_id = o.order_id
  join transit_targets tt on tt.pin_zone = o.pin_zone
  where o.status not in ('cancelled')
),
over as (
  select b.*,
         greatest(b.stock_wait_days - b.stock_target, 0)                     as stock_over,
         greatest(coalesce(b.fulfilment_days, 0) - b.fulfilment_target, 0)   as fulfilment_over,
         greatest(coalesce(b.transit_days, 0) - b.transit_target, 0)         as transit_over
  from base b
)
select o.*,
       o.stock_over > 0                                                     as stock_late,
       o.fulfilment_over > 0                                                as fulfilment_late,
       o.transit_over > 0                                                   as transit_late,
       (o.stock_over + o.fulfilment_over + o.transit_over) > 0              as is_late,
       round((o.stock_over + o.fulfilment_over + o.transit_over)::numeric, 1) as days_late,
       case when (o.stock_over + o.fulfilment_over + o.transit_over) = 0 then null
            when o.stock_over >= greatest(o.fulfilment_over, o.transit_over) then 'stock_wait'
            when o.fulfilment_over >= o.transit_over then 'fulfilment'
            else 'transit' end                                              as blamed_stage,
       date_trunc('week', o.placed_at)                                      as week
from over o;

-- Stages are pre-computed into a table (refresh_order_stages) so screens stay fast.
create table if not exists order_stages as select * from v_order_stages_calc with no data;
create index if not exists order_stages_order_idx on order_stages (order_id);
create index if not exists order_stages_vendor_idx on order_stages (vendor_id);

create or replace function refresh_order_stages() returns int
language plpgsql security definer set search_path = public as $$
declare n int;
begin
  delete from order_stages;
  insert into order_stages select * from v_order_stages_calc;
  get diagnostics n = row_count;
  return n;
end $$;
revoke all on function refresh_order_stages() from public, anon, authenticated;

create or replace view v_order_stages with (security_invoker = on) as select * from order_stages;

-- ---------- Neha's priority queue ----------
create or replace view v_issues with (security_invoker = on) as
with tagged as (
  -- Delay complaints are filed under whoever caused that order's delay (vendor, warehouse or courier);
  -- complaints about orders that were not late, or with no order linked, are left out.
  select it.source, it.item_id, it.category, it.urgency, it.sku_id,
         case when it.category = 'wismo' then st.blamed_stage else it.sub_tag end            as sub_tag,
         case when it.category <> 'wismo' then it.vendor_id
              when st.blamed_stage = 'stock_wait' then st.vendor_id
              when st.blamed_stage = 'fulfilment' then st.fc
              when st.blamed_stage = 'transit' then st.courier end                            as owner_id,
         coalesce(r.raised_at, t.created_at) as happened_at
  from item_tags it
  left join returns r on it.source = 'return' and r.return_id = it.item_id
  left join tickets t on it.source = 'ticket' and t.ticket_id = it.item_id
  left join v_order_stages st on it.category = 'wismo' and st.order_id = it.order_id
  where it.route = 'trusted'
    and it.category in ('fit', 'quality', 'colour_mismatch', 'wismo')
    and not (it.category = 'wismo' and st.blamed_stage is null)
),
grouped as (
  select category || '|' || coalesce(sub_tag, '-') || '|' || coalesce(owner_id, '-') as issue_key,
         category, sub_tag, owner_id as vendor_id,
         count(*) filter (where happened_at >= now() - interval '7 days')                                       as items_7d,
         count(*) filter (where happened_at >= now() - interval '14 days' and happened_at < now() - interval '7 days') as items_prev_7d,
         coalesce(avg((urgency = 'high')::int) filter (where happened_at >= now() - interval '7 days'), 0)     as share_high,
         count(*) filter (where source = 'return')                                                               as from_returns,
         count(*) filter (where source = 'ticket')                                                               as from_tickets,
         array_remove(array_agg(distinct sku_id), null)                                                          as skus
  from tagged
  group by 1, 2, 3, 4
),
scored as (
  select g.*,
         coalesce(w.weight, 1) as weight,
         least(3.0, case when g.items_prev_7d = 0 then 1.0
                         else g.items_7d::numeric / g.items_prev_7d end) as trend
  from grouped g
  left join category_weights w on w.category = g.category
)
select s.*,
       s.items_7d < coalesce((select value from app_settings where key = 'min_issue_items'), 5) as monitor,
       round(s.items_7d * s.weight * s.trend * (1 + 0.5 * s.share_high))    as score,
       coalesce(t.title,
                case when s.category = 'wismo' then
                       case s.sub_tag when 'stock_wait' then s.vendor_id || ' is late with stock'
                                      when 'fulfilment' then s.vendor_id || ' warehouse is slow to dispatch'
                                      else s.vendor_id || ' deliveries are late' end
                     else initcap(replace(coalesce(s.sub_tag, s.category), '_', ' ')) || coalesce(' · ' || s.vendor_id, '') end)
                                                                             as title,
       v.city                                                                as vendor_city,
       (select max(a.at) from issue_actions a where a.issue_key = s.issue_key) as last_action_at,
       (select a.action from issue_actions a where a.issue_key = s.issue_key order by a.at desc limit 1) as last_action
from scored s
left join issue_titles t on t.issue_key = s.issue_key
left join vendors v on v.vendor_id = s.vendor_id
where s.items_7d > 0;

-- WISMO tickets linked to an order
create or replace view v_wismo_orders with (security_invoker = on) as
select it.item_id as ticket_id, it.order_id, t.body, t.created_at
from item_tags it
join tickets t on t.ticket_id = it.item_id
where it.source = 'ticket' and it.category = 'wismo' and it.order_id is not null;

-- ---------- Delay scorecard ----------
-- Vendors are judged only on stock wait; couriers only on transit.
-- "Recurring" = late share above 15% in at least 3 of the last 4 weeks.
create or replace view v_vendor_scorecard with (security_invoker = on) as
with weekly as (
  select vendor_id, week, avg(stock_late::int) as late_share
  from v_order_stages
  where week >= date_trunc('week', now()) - interval '4 weeks'
  group by vendor_id, week
)
select s.vendor_id,
       v.city,
       count(*)                                                              as orders,
       round(100.0 * avg(s.stock_late::int), 0)                              as pct_late,
       round(avg(s.stock_over) filter (where s.stock_late)::numeric, 1)      as avg_days_late,
       round(100.0 * count(distinct w.ticket_id) / count(distinct s.order_id), 0) as wismo_per_100,
       mode() within group (order by s.blamed_stage) filter (where s.is_late) as top_stage,
       (select count(*) from weekly wk where wk.vendor_id = s.vendor_id and wk.late_share > 0.15) >= 3 as recurring
from v_order_stages s
join vendors v on v.vendor_id = s.vendor_id
left join v_wismo_orders w on w.order_id = s.order_id
group by s.vendor_id, v.city;

create or replace view v_courier_scorecard with (security_invoker = on) as
with weekly as (
  select courier, week, avg(transit_late::int) as late_share
  from v_order_stages
  where week >= date_trunc('week', now()) - interval '4 weeks' and handed_at is not null
  group by courier, week
),
zones as (
  select courier, pin_zone, avg(transit_late::int) as late_share, count(*) as n
  from v_order_stages where handed_at is not null
  group by courier, pin_zone
)
select s.courier,
       count(*)                                                              as orders,
       round(100.0 * avg(s.transit_late::int), 0)                            as pct_late,
       round(avg(s.transit_over) filter (where s.transit_late)::numeric, 1)  as avg_days_late,
       (select z.pin_zone || ' · ' || round(100 * z.late_share) || '% late'
          from zones z where z.courier = s.courier and z.n >= 5
          order by z.late_share desc limit 1)                                as worst_zone,
       (select count(*) from weekly wk where wk.courier = s.courier and wk.late_share > 0.15) >= 3 as recurring
from v_order_stages s
where s.handed_at is not null
group by s.courier;
