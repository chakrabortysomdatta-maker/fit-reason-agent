-- Fit-Reason Agent: core schema (Supabase / Postgres 15)
-- Run in order: 01_schema.sql, 02_views.sql, 03_security.sql

-- ---------- people and roles ----------
create table if not exists profiles (
  user_id      uuid primary key references auth.users (id) on delete cascade,
  display_name text not null,
  role         text not null check (role in ('category_head', 'cx_reviewer', 'supply_chain'))
);

-- ---------- catalogue ----------
create table if not exists vendors (
  vendor_id text primary key,                -- e.g. V-17
  name      text not null,
  city      text not null check (city in ('Tiruppur', 'Jaipur'))
);

create table if not exists size_charts (
  chart_id  text not null,
  size      text not null,                   -- XS, S, M, L, XL, or age band for kids (5-6Y)
  bust_in   numeric(4,1),
  waist_in  numeric(4,1),
  length_in numeric(4,1),
  primary key (chart_id, size)
);

create table if not exists category_size_medians (
  product_type text not null,                -- kurta, frock, palazzo, shirt ...
  size         text not null,
  bust_in      numeric(4,1),
  waist_in     numeric(4,1),
  length_in    numeric(4,1),
  primary key (product_type, size)
);

create table if not exists skus (
  sku_id       text primary key,             -- e.g. KRT-4471
  style_id     text not null,
  vendor_id    text not null references vendors,
  category     text not null check (category in ('womenswear', 'kidswear', 'menswear')),
  product_type text not null,
  name         text not null,
  colour       text,                         -- raw, as typed by the listing team
  fabric       text,
  price_inr    int  not null,
  chart_id     text,
  status       text not null default 'live' check (status in ('live', 'pulled')),
  launched_on  date not null
);

-- ---------- orders ----------
create table if not exists customers (
  customer_id  text primary key,             -- e.g. C-00123 (no names or phones stored)
  city         text not null,
  tier         int  not null check (tier in (1, 2, 3)),
  phone_masked text                          -- e.g. 98xxxxxx21
);

create table if not exists orders (
  order_id        text primary key,          -- e.g. DH-48213
  customer_id     text not null references customers,
  placed_at       timestamptz not null,
  payment_mode    text not null check (payment_mode in ('COD', 'Prepaid')),
  fc              text not null check (fc in ('Bhiwandi', 'Gurugram', 'Hyderabad')),
  courier         text not null check (courier in ('Delhivery', 'Shiprocket', 'Ekart')),
  pin_zone        text not null check (pin_zone in ('north', 'south', 'east', 'west', 'north_east')),
  order_value_inr int  not null,
  status          text not null check (status in ('placed', 'stock_available', 'shipped', 'delivered', 'rto', 'cancelled'))
);

create table if not exists order_lines (
  line_id   text primary key,                -- e.g. DH-48213-1
  order_id  text not null references orders,
  sku_id    text not null references skus,
  size      text not null,
  qty       int  not null default 1,
  price_inr int  not null
);

create table if not exists order_events (
  event_id bigint generated always as identity primary key,
  order_id text not null references orders,
  status   text not null check (status in ('placed', 'stock_available', 'handed_to_courier', 'in_transit',
                                           'out_for_delivery', 'delivered', 'rto')),
  at       timestamptz not null
);
create index if not exists order_events_order_idx on order_events (order_id, at);

-- ---------- customer text ----------
create table if not exists returns (
  return_id         text primary key,        -- e.g. R-10021
  line_id           text not null references order_lines,
  reason_dropdown   text not null,           -- size issue, damaged, not as described, other ...
  other_text        text,                    -- free text when 'Other'
  raised_at         timestamptz not null,
  status            text not null check (status in ('requested', 'picked_up', 'inspection_pending', 'refunded')),
  refund_amount_inr int,
  refunded_at       timestamptz
);

create table if not exists tickets (
  ticket_id   text primary key,              -- e.g. T-30412
  channel     text not null check (channel in ('freshdesk', 'whatsapp')),
  customer_id text references customers,
  order_id    text references orders,        -- often missing; the pipeline tries to extract it
  body        text not null,
  created_at  timestamptz not null
);

create table if not exists policies (
  policy_key text primary key,               -- exchange, refund, cod
  body       text not null
);

-- ---------- targets set by the business ----------
create table if not exists stage_targets (
  stage       text primary key check (stage in ('stock_wait', 'fulfilment')),
  target_days numeric(4,1) not null
);
create table if not exists transit_targets (
  pin_zone text primary key,
  max_days int not null
);
create table if not exists category_weights (
  category text primary key,
  weight   numeric(3,1) not null
);

-- ---------- pipeline outputs ----------
create table if not exists runs (
  run_id       uuid primary key default gen_random_uuid(),
  kind         text not null check (kind in ('tag', 'draft', 'live')),
  started_at   timestamptz not null default now(),
  finished_at  timestamptz,
  items        int not null default 0,
  unclassified int not null default 0,
  tokens       jsonb not null default '{}'::jsonb,   -- {"claude-haiku-4-5": {"in": 0, "out": 0}, ...}
  cost_inr     numeric(10,2) not null default 0,
  status       text not null default 'running' check (status in ('running', 'done', 'failed'))
);

create table if not exists item_tags (
  source         text not null check (source in ('return', 'ticket')),
  item_id        text not null,
  category       text check (category in ('fit', 'quality', 'colour_mismatch', 'wismo', 'refund',
                                          'exchange', 'cod_payment', 'other')),
  sub_tag        text,                       -- runs_small, runs_large, length_short, fabric_feel ...
  urgency        text check (urgency in ('low', 'medium', 'high')),
  language       text check (language in ('hinglish', 'hindi', 'english', 'other')),
  order_id       text,                       -- extracted or from the source row
  sku_id         text,                       -- joined in code
  vendor_id      text,                       -- joined in code
  confidence     numeric(3,2),
  evidence_span  text,
  route          text not null check (route in ('trusted', 'check_tag', 'unclassified')),
  model          text,
  prompt_version text,
  run_id         uuid references runs,
  tagged_at      timestamptz not null default now(),
  primary key (source, item_id)
);

create table if not exists issue_titles (
  issue_key  text primary key,               -- category|sub_tag|vendor_id
  title      text not null,
  run_id     uuid references runs,
  updated_at timestamptz not null default now()
);

create table if not exists issue_actions (
  action_id  bigint generated always as identity primary key,
  issue_key  text not null,
  action     text not null check (action in ('fix', 'escalate', 'monitor', 'wrong_tag')),
  note       text,
  actor      uuid not null default auth.uid() references auth.users,
  actor_name text not null,
  at         timestamptz not null default now()
);

create table if not exists guidance_drafts (
  draft_id           uuid primary key default gen_random_uuid(),
  ticket_id          text references tickets,  -- null for "Try a message"
  message_text       text not null,
  category           text,
  language           text,
  facts              jsonb not null default '{}'::jsonb,
  reply              text,                     -- null when no safe reply was possible
  attempts           jsonb not null default '[]'::jsonb,  -- [{reply, problems[]}]
  check_passed       boolean,
  status             text not null check (status in ('drafted', 'needs_human', 'unclassified')),
  needs_human_reason text,
  cost_inr           numeric(8,2) not null default 0,
  run_id             uuid references runs,
  created_at         timestamptz not null default now()
);

create table if not exists draft_reviews (
  review_id     bigint generated always as identity primary key,
  draft_id      uuid not null references guidance_drafts on delete cascade,
  rating        text not null check (rating in ('send_as_is', 'needs_edit', 'wrong')),
  edited_text   text,
  reviewer      uuid not null default auth.uid() references auth.users,
  reviewer_name text not null,
  at            timestamptz not null default now()
);
