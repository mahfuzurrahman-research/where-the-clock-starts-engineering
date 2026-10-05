-- Two independent as-of reconstructions from the raw log: observation and baseline.
CREATE TABLE sql_ordered AS
SELECT e.*, p.kind, p.as_of, p.lateness_seconds, unixepoch(e.event_time) AS event_epoch,
       unixepoch(e.recorded_at) AS recorded_epoch,
       ROW_NUMBER() OVER(PARTITION BY p.kind ORDER BY delivery_seq,input_index) AS ingest_index,
       ROW_NUMBER() OVER(PARTITION BY p.kind,delivery_id ORDER BY input_index) AS delivery_rank,
       ROW_NUMBER() OVER(PARTITION BY p.kind,event_id,revision ORDER BY delivery_seq,input_index) AS version_rank,
       MAX(revision) OVER(PARTITION BY p.kind,event_id ORDER BY delivery_seq,input_index
                         ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS previous_revision
FROM raw_events e CROSS JOIN snapshot_parameters p WHERE unixepoch(e.recorded_at)<=p.as_of;

CREATE TABLE sql_actions AS
SELECT *, CASE WHEN delivery_rank>1 THEN 'duplicate_delivery'
               WHEN version_rank>1 THEN 'duplicate_version'
               WHEN revision<previous_revision THEN 'stale_revision' ELSE 'accepted' END AS action
FROM sql_ordered;

CREATE TABLE sql_watermarks AS
SELECT *, MAX(CASE WHEN action='accepted' AND operation='UPSERT' THEN event_epoch END)
          OVER(PARTITION BY kind ORDER BY ingest_index ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)-lateness_seconds AS watermark_before,
          MAX(CASE WHEN action='accepted' AND operation='UPSERT' THEN event_epoch END)
          OVER(PARTITION BY kind ORDER BY ingest_index ROWS UNBOUNDED PRECEDING)-lateness_seconds AS watermark_after,
          SUM(action='accepted') OVER(PARTITION BY kind,case_id ORDER BY ingest_index ROWS UNBOUNDED PRECEDING) AS case_revision,
          CASE WHEN operation='UPSERT' THEN event_epoch ELSE
              (SELECT t.event_epoch FROM sql_actions t WHERE t.kind=s.kind AND t.event_id=s.event_id
               AND t.action='accepted' AND t.ingest_index<s.ingest_index ORDER BY t.ingest_index DESC LIMIT 1) END AS lateness_epoch
FROM sql_actions s;

CREATE TABLE sql_audit AS
SELECT *, CASE WHEN action='accepted' AND lateness_epoch<watermark_before THEN 1 ELSE 0 END AS late_update
FROM sql_watermarks;

CREATE TABLE sql_latest AS
SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER(PARTITION BY kind,event_id ORDER BY revision DESC,delivery_seq,input_index) AS latest_rank
    FROM sql_actions) WHERE latest_rank=1;

CREATE TABLE sql_stage_counts AS
SELECT kind,case_id,event_type,COUNT(*) AS n,MIN(event_epoch) AS event_epoch,
       CASE event_type WHEN 'ISSUED' THEN 1 WHEN 'NOTIFIED' THEN 2 WHEN 'VISITED' THEN 3
                       WHEN 'REPORTED' THEN 4 WHEN 'DECIDED' THEN 5 END AS stage_index
FROM sql_latest WHERE operation='UPSERT' GROUP BY kind,case_id,event_type;

CREATE TABLE sql_case_features AS
SELECT c.case_id,c.service_group,p.kind,p.as_of,
       COALESCE(SUM(s.n),0) AS active_count,COUNT(s.event_type) AS present_count,COALESCE(MAX(s.stage_index),0) AS last_stage,
       COALESCE(MAX(s.n),0)>1 AS ambiguous_stage,
       CASE WHEN COUNT(s.event_type)<>COALESCE(MAX(s.stage_index),0) THEN 1 ELSE 0 END AS missing_predecessor,
       EXISTS(SELECT 1 FROM sql_stage_counts a JOIN sql_stage_counts b ON a.kind=b.kind AND a.case_id=b.case_id
              WHERE a.kind=p.kind AND a.case_id=c.case_id AND a.n=1 AND b.n=1
                AND a.stage_index<b.stage_index AND a.event_epoch>b.event_epoch) AS stage_reversal,
       MAX(CASE WHEN s.event_type='ISSUED' AND s.n=1 THEN s.event_epoch END) AS issue_epoch,
       MAX(CASE WHEN s.event_type='NOTIFIED' AND s.n=1 THEN s.event_epoch END) AS notification_epoch,
       MAX(CASE WHEN s.event_type='DECIDED' AND s.n=1 THEN s.event_epoch END) AS decision_epoch,
       (SELECT COUNT(*) FROM sql_actions a WHERE a.kind=p.kind AND a.case_id=c.case_id AND a.action='accepted') AS projection_revision,
       EXISTS(SELECT 1 FROM sql_latest t WHERE t.kind=p.kind AND t.case_id=c.case_id
               AND t.event_type='DECIDED' AND t.operation='RETRACT') AS decision_retracted
FROM case_catalog c CROSS JOIN snapshot_parameters p
LEFT JOIN sql_stage_counts s ON s.kind=p.kind AND s.case_id=c.case_id
WHERE unixepoch(c.registered_at)<=p.as_of GROUP BY c.case_id,c.service_group,p.kind,p.as_of;

CREATE TABLE sql_case_states AS
SELECT *, CASE WHEN active_count=0 THEN 'EMPTY'
               WHEN ambiguous_stage OR missing_predecessor OR stage_reversal THEN 'REVIEW'
               WHEN present_count=5 THEN 'COMPLETE' ELSE 'OPEN' END AS state
FROM sql_case_features;

CREATE TABLE sql_case_clocks AS
SELECT *, CASE WHEN state='COMPLETE' THEN (decision_epoch-issue_epoch)/3600.0 END AS issue_to_decision_hours,
          CASE WHEN state='COMPLETE' THEN (decision_epoch-notification_epoch)/3600.0 END AS notification_to_decision_hours,
          CASE WHEN state='OPEN' THEN (as_of-issue_epoch)/3600.0 END AS issue_age_hours,
          CASE WHEN state='OPEN' THEN (as_of-notification_epoch)/3600.0 END AS notification_age_hours
FROM sql_case_states;

CREATE TABLE sql_stage_durations AS
SELECT a.case_id,a.event_type AS from_stage,b.event_type AS to_stage,
       (b.event_epoch-a.event_epoch)/3600.0 AS duration_hours
FROM sql_stage_counts a JOIN sql_stage_counts b ON a.kind=b.kind AND a.case_id=b.case_id AND b.stage_index=a.stage_index+1
JOIN sql_case_clocks c ON c.kind=a.kind AND c.case_id=a.case_id
WHERE a.kind='OBS' AND c.state IN('COMPLETE','OPEN');

-- Only a scalar math callback is shared; membership, medians/MADs and scores are SQL-derived.
CREATE TABLE sql_baseline_values AS
SELECT case_id,service_group,log1p(notification_to_decision_hours) AS value,
       ROW_NUMBER() OVER(PARTITION BY service_group ORDER BY log1p(notification_to_decision_hours),case_id) AS position,
       COUNT(*) OVER(PARTITION BY service_group) AS n
FROM sql_case_clocks WHERE kind='BASE' AND state='COMPLETE';
CREATE TABLE sql_centers AS
SELECT service_group,AVG(value) AS center,MAX(n) AS n FROM sql_baseline_values
WHERE position IN((n+1)/2,(n+2)/2) GROUP BY service_group;
CREATE TABLE sql_deviations AS
SELECT v.*,c.center,ABS(v.value-c.center) AS deviation,
       ROW_NUMBER() OVER(PARTITION BY v.service_group ORDER BY ABS(v.value-c.center),v.case_id) AS mad_position
FROM sql_baseline_values v JOIN sql_centers c USING(service_group);
CREATE TABLE sql_profiles AS
SELECT service_group,MAX(n) AS n,MAX(center) AS center,AVG(deviation) AS mad,
       MAX(1.4826*AVG(deviation),(SELECT mad_scale_floor FROM policy_parameters)) AS scale
FROM sql_deviations WHERE mad_position IN((n+1)/2,(n+2)/2) GROUP BY service_group;
CREATE TABLE sql_scores AS
SELECT c.case_id,c.service_group,c.notification_to_decision_hours AS duration_hours,
       p.center,p.scale,(log1p(c.notification_to_decision_hours)-p.center)/p.scale AS score,
       CASE WHEN (log1p(c.notification_to_decision_hours)-p.center)/p.scale > t.duration_score_threshold
             AND c.notification_to_decision_hours>t.absolute_duration_hours THEN 1 ELSE 0 END AS flagged
FROM sql_case_clocks c JOIN sql_profiles p USING(service_group) CROSS JOIN policy_parameters t
WHERE c.kind='OBS' AND c.state='COMPLETE' AND c.case_id NOT IN(SELECT case_id FROM sql_baseline_values);

CREATE TABLE sql_expected_alerts AS
SELECT case_id,'P1' AS priority,'data_quality' AS category,'no_observed_events' AS reason
FROM sql_case_clocks WHERE kind='OBS' AND state='EMPTY'
UNION ALL SELECT case_id,'P1','data_quality','ambiguous_stage' FROM sql_case_clocks WHERE kind='OBS' AND ambiguous_stage
UNION ALL SELECT case_id,'P1','data_quality','missing_predecessor' FROM sql_case_clocks WHERE kind='OBS' AND missing_predecessor
UNION ALL SELECT case_id,'P1','data_quality','stage_reversal' FROM sql_case_clocks WHERE kind='OBS' AND stage_reversal
UNION ALL SELECT case_id,'P2','process_pattern','decision_withdrawn' FROM sql_case_clocks WHERE kind='OBS' AND state='OPEN' AND decision_retracted
UNION ALL SELECT case_id,'P2','process_pattern','aged_open_case' FROM sql_case_clocks
 WHERE kind='OBS' AND state='OPEN' AND notification_age_hours>(SELECT open_age_hours FROM policy_parameters)
UNION ALL SELECT case_id,'P2','process_pattern','awaiting_notification' FROM sql_case_clocks
 WHERE kind='OBS' AND state='OPEN' AND notification_epoch IS NULL AND issue_age_hours>(SELECT notification_wait_hours FROM policy_parameters)
UNION ALL SELECT DISTINCT case_id,'P3','delivery_quality',action FROM sql_actions
 WHERE kind='OBS' AND action IN('duplicate_delivery','duplicate_version','stale_revision')
UNION ALL SELECT DISTINCT case_id,'P3','delivery_quality','late_event_update' FROM sql_audit WHERE kind='OBS' AND late_update=1
UNION ALL SELECT DISTINCT case_id,'P3','delivery_quality','revised_event_record' FROM sql_actions WHERE kind='OBS' AND action='accepted' AND revision>1
UNION ALL SELECT case_id,'P2','duration_candidate','duration_upper_tail' FROM sql_scores WHERE flagged=1;

CREATE TABLE stream_quality_results AS
SELECT 'E01_case_keys' AS check_name,COUNT(*)-COUNT(DISTINCT case_id) AS failures FROM case_catalog
UNION ALL SELECT 'E02_source_markers',(SELECT COUNT(*) FROM case_catalog WHERE synthetic_record<>'true' OR synthetic_record IS NULL)
 + (SELECT COUNT(*) FROM raw_events WHERE synthetic_record<>'true' OR synthetic_record IS NULL)
UNION ALL SELECT 'E03_source_timestamp_domains',COUNT(*) FROM raw_events e LEFT JOIN case_catalog c USING(case_id)
 WHERE c.case_id IS NULL OR unixepoch(e.recorded_at) IS NULL OR unixepoch(e.recorded_at)<unixepoch(c.registered_at)
 OR (operation='UPSERT' AND (unixepoch(event_time) IS NULL OR unixepoch(event_time)>unixepoch(recorded_at)))
 OR (operation='RETRACT' AND event_time IS NOT NULL)
UNION ALL SELECT 'E04_source_domains',COUNT(*) FROM raw_events WHERE event_type NOT IN('ISSUED','NOTIFIED','VISITED','REPORTED','DECIDED')
 OR operation NOT IN('UPSERT','RETRACT') OR revision<=0 OR delivery_seq<=0
UNION ALL SELECT 'E05_delivery_sequence_consistency',COUNT(*) FROM (
 SELECT delivery_seq FROM raw_events GROUP BY delivery_seq HAVING COUNT(DISTINCT delivery_id)>1)
UNION ALL SELECT 'E06_audit_inventory',ABS((SELECT COUNT(*) FROM ingest_audit)-(SELECT COUNT(*) FROM sql_audit WHERE kind='OBS'))
 + (SELECT COUNT(*)-COUNT(DISTINCT ingest_index) FROM ingest_audit)
UNION ALL SELECT 'E07_audit_action_reconstruction',COUNT(*) FROM sql_audit s LEFT JOIN ingest_audit p USING(ingest_index)
 WHERE s.kind='OBS' AND (p.ingest_index IS NULL OR p.action IS NOT s.action OR p.delivery_id IS NOT s.delivery_id
                        OR p.event_id IS NOT s.event_id OR p.revision IS NOT s.revision)
UNION ALL SELECT 'E08_watermark_and_lateness',COUNT(*) FROM sql_audit s JOIN ingest_audit p USING(ingest_index)
 WHERE s.kind='OBS' AND (p.late_update IS NOT s.late_update OR unixepoch(p.watermark_before) IS NOT s.watermark_before
 OR unixepoch(p.watermark_after) IS NOT s.watermark_after OR unixepoch(p.lateness_event_time) IS NOT s.lateness_epoch)
UNION ALL SELECT 'E09_projection_revision',COUNT(*) FROM sql_audit s JOIN ingest_audit p USING(ingest_index)
 WHERE s.kind='OBS' AND p.case_revision IS NOT s.case_revision
UNION ALL SELECT 'E10_effective_event_inventory',ABS((SELECT COUNT(*) FROM effective_events)-(SELECT COUNT(*) FROM sql_latest WHERE kind='OBS'))
 + (SELECT COUNT(*)-COUNT(DISTINCT event_id) FROM effective_events)
UNION ALL SELECT 'E11_latest_revision_and_tombstones',COUNT(*) FROM sql_latest s LEFT JOIN effective_events p USING(event_id)
 WHERE s.kind='OBS' AND (p.event_id IS NULL OR p.revision IS NOT s.revision OR p.operation IS NOT s.operation
 OR p.case_id IS NOT s.case_id OR p.event_type IS NOT s.event_type OR unixepoch(p.event_time) IS NOT s.event_epoch)
UNION ALL SELECT 'E12_case_clock_inventory',ABS((SELECT COUNT(*) FROM case_clocks)-(SELECT COUNT(*) FROM sql_case_clocks WHERE kind='OBS'))
 + (SELECT COUNT(*)-COUNT(DISTINCT case_id) FROM case_clocks)
UNION ALL SELECT 'E13_case_state_reconstruction',COUNT(*) FROM sql_case_clocks s LEFT JOIN case_clocks p USING(case_id)
 WHERE s.kind='OBS' AND (p.case_id IS NULL OR p.state IS NOT s.state OR p.service_group IS NOT s.service_group)
UNION ALL SELECT 'E14_clock_anchor_and_revision',COUNT(*) FROM sql_case_clocks s JOIN case_clocks p USING(case_id)
 WHERE s.kind='OBS' AND (unixepoch(p.issue_time) IS NOT s.issue_epoch OR unixepoch(p.notification_time) IS NOT s.notification_epoch
 OR unixepoch(p.decision_time) IS NOT s.decision_epoch OR p.projection_revision IS NOT s.projection_revision
 OR p.decision_retracted IS NOT s.decision_retracted)
UNION ALL SELECT 'E15_clock_duration_reconstruction',COUNT(*) FROM sql_case_clocks s JOIN case_clocks p USING(case_id)
 WHERE s.kind='OBS' AND ((p.issue_to_decision_hours IS NULL)<>(s.issue_to_decision_hours IS NULL)
 OR (p.notification_to_decision_hours IS NULL)<>(s.notification_to_decision_hours IS NULL)
 OR ABS(p.issue_to_decision_hours-s.issue_to_decision_hours)>1e-10
 OR ABS(p.notification_to_decision_hours-s.notification_to_decision_hours)>1e-10)
UNION ALL SELECT 'E16_open_age_reconstruction',COUNT(*) FROM sql_case_clocks s JOIN case_clocks p USING(case_id)
 WHERE s.kind='OBS' AND ((p.issue_age_hours IS NULL)<>(s.issue_age_hours IS NULL)
 OR (p.notification_age_hours IS NULL)<>(s.notification_age_hours IS NULL)
 OR ABS(p.issue_age_hours-s.issue_age_hours)>1e-10 OR ABS(p.notification_age_hours-s.notification_age_hours)>1e-10)
UNION ALL SELECT 'E17_stage_duration_inventory',
 (SELECT COUNT(*) FROM sql_stage_durations s LEFT JOIN stage_durations p USING(case_id,from_stage,to_stage)
  WHERE p.case_id IS NULL OR p.duration_hours IS NULL OR ABS(s.duration_hours-p.duration_hours)>1e-10)
 + (SELECT COUNT(*) FROM stage_durations p LEFT JOIN sql_stage_durations s USING(case_id,from_stage,to_stage) WHERE s.case_id IS NULL)
 + (SELECT COUNT(*)-COUNT(DISTINCT case_id||':'||from_stage||':'||to_stage) FROM stage_durations)
UNION ALL SELECT 'E18_completed_clock_partition',COUNT(*) FROM case_clocks c
 WHERE state='COMPLETE' AND (ABS(issue_to_decision_hours-(SELECT SUM(duration_hours) FROM stage_durations d WHERE d.case_id=c.case_id))>1e-10
 OR ABS(notification_to_decision_hours-(SELECT SUM(duration_hours) FROM stage_durations d WHERE d.case_id=c.case_id AND from_stage<>'ISSUED'))>1e-10)
UNION ALL SELECT 'E19_completed_open_separation',COUNT(*) FROM case_clocks WHERE
 (state<>'COMPLETE' AND (issue_to_decision_hours IS NOT NULL OR notification_to_decision_hours IS NOT NULL))
 OR (state<>'OPEN' AND (issue_age_hours IS NOT NULL OR notification_age_hours IS NOT NULL))
UNION ALL SELECT 'E20_frozen_training_membership',
 (SELECT COUNT(*) FROM sql_baseline_values s LEFT JOIN baseline_members p USING(case_id) WHERE p.case_id IS NULL OR p.service_group IS NOT s.service_group)
 + (SELECT COUNT(*) FROM baseline_members p LEFT JOIN sql_baseline_values s USING(case_id) WHERE s.case_id IS NULL)
 + (SELECT COUNT(*)-COUNT(DISTINCT case_id) FROM baseline_members)
UNION ALL SELECT 'E21_historical_profile_reconstruction',COUNT(*) FROM sql_profiles s LEFT JOIN baseline_profiles p USING(service_group)
 WHERE p.service_group IS NULL OR p.log_median IS NULL OR p.log_mad IS NULL OR p.scale IS NULL
 OR p.count IS NOT s.n OR ABS(p.log_median-s.center)>1e-10
 OR ABS(p.log_mad-s.mad)>1e-10 OR ABS(p.scale-s.scale)>1e-10
UNION ALL SELECT 'E22_score_inventory',
 (SELECT COUNT(*) FROM sql_scores s LEFT JOIN duration_scores p USING(case_id) WHERE p.case_id IS NULL)
 + (SELECT COUNT(*) FROM duration_scores p LEFT JOIN sql_scores s USING(case_id) WHERE s.case_id IS NULL)
 + (SELECT COUNT(*)-COUNT(DISTINCT case_id) FROM duration_scores)
UNION ALL SELECT 'E23_duration_score_reconstruction',COUNT(*) FROM sql_scores s JOIN duration_scores p USING(case_id)
 WHERE p.duration_hours IS NULL OR p.upper_tail_score IS NULL OR p.baseline_scale IS NULL
 OR p.log_duration IS NULL OR p.baseline_median IS NULL OR p.score_threshold IS NULL OR p.absolute_floor_hours IS NULL
 OR p.service_group IS NOT s.service_group OR ABS(p.log_duration-log1p(s.duration_hours))>1e-10
 OR ABS(p.score_threshold-(SELECT duration_score_threshold FROM policy_parameters))>1e-10
 OR ABS(p.absolute_floor_hours-(SELECT absolute_duration_hours FROM policy_parameters))>1e-10
 OR ABS(p.duration_hours-s.duration_hours)>1e-10 OR ABS(p.upper_tail_score-s.score)>1e-10
 OR ABS(p.baseline_median-s.center)>1e-10 OR ABS(p.baseline_scale-s.scale)>1e-10 OR p.flagged IS NOT s.flagged
 OR unixepoch(p.baseline_cutoff) IS NOT (SELECT as_of FROM snapshot_parameters WHERE kind='BASE')
 OR p.baseline_hash IS NOT (SELECT baseline_hash FROM policy_parameters)
UNION ALL SELECT 'E24_review_only_claims',COUNT(*) FROM review_queue WHERE status IS NOT 'review_required'
 OR establishes_legal_breach IS NOT 'false' OR establishes_wrongdoing IS NOT 'false' OR synthetic_record IS NOT 'true'
UNION ALL SELECT 'E25_review_queue_reconstruction',
 (SELECT COUNT(*) FROM sql_expected_alerts s LEFT JOIN review_queue p USING(case_id,reason)
  WHERE p.case_id IS NULL OR p.priority IS NOT s.priority OR p.category IS NOT s.category)
 + (SELECT COUNT(*) FROM review_queue p LEFT JOIN sql_expected_alerts s USING(case_id,reason) WHERE s.case_id IS NULL)
 + (SELECT COUNT(*)-COUNT(DISTINCT case_id||':'||reason) FROM review_queue)
UNION ALL SELECT 'E26_review_evidence_and_keys',COUNT(*)-COUNT(DISTINCT alert_id)
 + COALESCE(SUM(CASE WHEN NOT json_valid(evidence_json) THEN 1 ELSE 0 END),0) FROM review_queue;
