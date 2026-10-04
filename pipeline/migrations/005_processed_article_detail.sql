-- Why an article was skipped, where there is more to say than the outcome
-- (e.g. the prefilter's Jev confidence), so skips can be reviewed.
alter table processed_articles add column if not exists detail text;
