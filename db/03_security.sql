-- Fit-Reason Agent: row-level security.
-- The Streamlit app queries as the signed-in user (anon key + user JWT), so these rules decide
-- what each person can see. The pipeline uses the service key server-side and bypasses RLS.

create or replace function app_role() returns text
language sql stable security definer set search_path = public as $$
  select role from profiles where user_id = auth.uid()
$$;

-- Turn RLS on everywhere: no policy = no access.
do $$
declare t text;
begin
  foreach t in array array['profiles', 'vendors', 'size_charts', 'category_size_medians', 'skus', 'customers',
                           'orders', 'order_lines', 'order_events', 'returns', 'tickets', 'policies',
                           'stage_targets', 'transit_targets', 'category_weights', 'runs', 'item_tags',
                           'issue_titles', 'issue_actions', 'guidance_drafts', 'draft_reviews']
  loop
    execute format('alter table %I enable row level security', t);
  end loop;
end $$;

-- Everyone signed in can read their own profile.
drop policy if exists own_profile on profiles;
create policy own_profile on profiles for select using (user_id = auth.uid());

-- Neha (category_head) and supply chain: catalogue, orders, returns, tags, issues, delay data.
do $$
declare t text;
begin
  foreach t in array array['vendors', 'size_charts', 'category_size_medians', 'skus', 'orders', 'order_lines',
                           'order_events', 'returns', 'item_tags', 'issue_titles', 'stage_targets',
                           'transit_targets', 'category_weights', 'runs']
  loop
    execute format('drop policy if exists analyst_read on %I', t);
    execute format($p$create policy analyst_read on %I for select
                      using (app_role() in ('category_head', 'supply_chain'))$p$, t);
  end loop;
end $$;

-- Tickets: analysts need them for WISMO links; CX reviewers need them for the guidance list.
drop policy if exists ticket_read on tickets;
create policy ticket_read on tickets for select
  using (app_role() in ('category_head', 'supply_chain', 'cx_reviewer'));

-- Neha's actions on issues.
drop policy if exists issue_actions_read on issue_actions;
create policy issue_actions_read on issue_actions for select
  using (app_role() in ('category_head', 'supply_chain'));
drop policy if exists issue_actions_write on issue_actions;
create policy issue_actions_write on issue_actions for insert
  with check (app_role() = 'category_head' and actor = auth.uid());

-- Ms Chhaya Gupta (cx_reviewer): reply suggestions and her ratings only.
drop policy if exists drafts_read on guidance_drafts;
create policy drafts_read on guidance_drafts for select
  using (app_role() = 'cx_reviewer');
drop policy if exists policies_read on policies;
create policy policies_read on policies for select
  using (app_role() = 'cx_reviewer');
drop policy if exists reviews_read on draft_reviews;
create policy reviews_read on draft_reviews for select
  using (app_role() = 'cx_reviewer');
drop policy if exists reviews_write on draft_reviews;
create policy reviews_write on draft_reviews for insert
  with check (app_role() = 'cx_reviewer' and reviewer = auth.uid());
