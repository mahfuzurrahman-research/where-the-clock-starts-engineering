CREATE TABLE quality_results AS
SELECT 'stage_key_coverage' check_name,COUNT(*) violations FROM cases c LEFT JOIN stages s USING(case_id) WHERE s.case_id IS NULL
UNION ALL SELECT 'no_orphan_stages',COUNT(*) FROM stages s LEFT JOIN cases c USING(case_id) WHERE c.case_id IS NULL
UNION ALL SELECT 'primary_indicator_agreement',COUNT(*) FROM cases c JOIN stages s USING(case_id) WHERE c.primary_flag<>s.primary_flag
UNION ALL SELECT 'process_requires_primary',COUNT(*) FROM cases WHERE process_flag=1 AND primary_flag=0
UNION ALL SELECT 'payment_requires_process',COUNT(*) FROM cases WHERE payment_flag=1 AND process_flag=0
UNION ALL SELECT 'stage_requires_process',COUNT(*) FROM stages s JOIN cases c USING(case_id) WHERE s.stage_eligible=1 AND c.process_flag=0
UNION ALL SELECT 'eligible_clock_flag_required',COUNT(*) FROM stages WHERE stage_eligible=1 AND clock_flag IS NULL
UNION ALL SELECT 'nonstage_clock_flag_blank',COUNT(*) FROM stages WHERE stage_eligible=0 AND clock_flag IS NOT NULL
UNION ALL SELECT 'eligible_clock_complete',COUNT(*) FROM stages WHERE stage_eligible=1 AND (issue_date IS NULL OR notification_date IS NULL OR visit_date IS NULL OR report_date IS NULL OR decision_date IS NULL)
UNION ALL SELECT 'chronology_ordered',COUNT(*) FROM stages WHERE stage_eligible=1 AND NOT(issue_date<=notification_date AND notification_date<=visit_date AND visit_date<=report_date AND report_date<=decision_date)
UNION ALL SELECT 'process_stage_count_reconciles',CASE WHEN (SELECT SUM(process_flag) FROM cases)=(SELECT SUM(stage_eligible) FROM stages) THEN 0 ELSE 1 END
UNION ALL SELECT 'clock_partition_reconciles',CASE WHEN (SELECT COUNT(*) FROM stages WHERE stage_eligible=1)=(SELECT COUNT(*) FROM stages WHERE stage_eligible=1 AND clock_flag IN(0,1)) THEN 0 ELSE 1 END;
