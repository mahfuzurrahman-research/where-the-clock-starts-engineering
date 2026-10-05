PRAGMA foreign_keys=ON;
CREATE TABLE cases(case_id TEXT PRIMARY KEY,decision_period TEXT NOT NULL,primary_flag INTEGER NOT NULL CHECK(primary_flag IN(0,1)),process_flag INTEGER NOT NULL CHECK(process_flag IN(0,1)),payment_flag INTEGER NOT NULL CHECK(payment_flag IN(0,1)),inspection_count INTEGER NOT NULL CHECK(inspection_count>=0),reported_delay_days REAL);
CREATE TABLE stages(case_id TEXT PRIMARY KEY,primary_flag INTEGER NOT NULL CHECK(primary_flag IN(0,1)),stage_eligible INTEGER NOT NULL CHECK(stage_eligible IN(0,1)),second_stage_indicator TEXT NOT NULL,clock_flag INTEGER CHECK(clock_flag IN(0,1)),issue_date TEXT,notification_date TEXT,visit_date TEXT,report_date TEXT,decision_date TEXT,FOREIGN KEY(case_id) REFERENCES cases(case_id));
CREATE INDEX idx_cases_period ON cases(decision_period);
CREATE INDEX idx_stages_eligible_clock ON stages(stage_eligible,clock_flag);
