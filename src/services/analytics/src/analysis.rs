use serde_json::{Map, Value};

use crate::args::{self, ExerciseArgs, SectionArgs, SuggestArgs};
use crate::assemble::{self, Loaded, Scope};
use crate::calc::progression::{progression_rate, rpe_drift};
use crate::calc::projection::multiplier_suggestions;
use crate::engine::{Engine, to_value};
use crate::error::Error;
use crate::model::{ProgramData, Session};
use crate::sections::{self, Params};
use crate::source::Window;
use crate::util::parse_date;

impl Engine {
    pub async fn supplied_or_loaded(
        &self,
        athlete: &str,
        program: Option<Value>,
        sessions: Option<Value>,
        scope: Scope<'_>,
    ) -> Result<Loaded, Error> {
        let Some(mut program) = program.filter(Value::is_object) else {
            return self.load(athlete, &Window::default(), scope).await;
        };
        let listed = match sessions {
            Some(Value::Array(items)) => items,
            _ => match program.get_mut("sessions").map(Value::take) {
                Some(Value::Array(items)) => items,
                _ => Vec::new(),
            },
        };
        let data = ProgramData::from_value(
            &program,
            listed.into_iter().map(Session::from_value).collect(),
        );
        let glossary = assemble::glossary(self.source.glossary(athlete).await?);
        Ok(Loaded {
            program: data,
            glossary,
            weight_log: Vec::new(),
            goals: Vec::new(),
        })
    }

    fn params(args: &SectionArgs) -> Params {
        Params {
            weeks: args.weeks,
            block: Some(args.block.clone()),
            window_start: args.window_start.clone(),
            window_end: args.window_end.clone(),
            ref_date: args.ref_date.clone(),
            week_start: args.week_start,
            week_end: args.week_end,
        }
    }

    pub async fn analysis_section(&self, arguments: Map<String, Value>) -> Result<Value, Error> {
        let args: SectionArgs = args::parse(arguments)?;
        let params = Self::params(&args);
        let loaded = self
            .supplied_or_loaded(&args.pk, args.program, args.sessions, Scope::Everything)
            .await?;
        sections::compute(self.env(&loaded), &loaded.program, &args.section, &params)
    }

    pub async fn weekly_analysis(&self, arguments: Map<String, Value>) -> Result<Value, Error> {
        let args: SectionArgs = args::parse(arguments)?;
        let params = Self::params(&args);
        let loaded = self
            .supplied_or_loaded(&args.pk, args.program, args.sessions, Scope::Everything)
            .await?;
        sections::compute_all(self.env(&loaded), &loaded.program, &params).map(Value::Object)
    }

    fn reference(&self, first: Option<&str>, second: Option<&str>) -> chrono::NaiveDate {
        [first, second]
            .into_iter()
            .flatten()
            .find(|text| !text.is_empty())
            .and_then(parse_date)
            .unwrap_or_else(|| self.clock.today())
    }

    pub async fn progression(&self, arguments: Map<String, Value>) -> Result<Value, Error> {
        let args: ExerciseArgs = args::parse(arguments)?;
        let reference = self.reference(args.reference_date.as_deref(), args.ref_date.as_deref());
        let loaded = self
            .supplied_or_loaded(&args.pk, args.program, args.sessions, Scope::Stored)
            .await?;
        let sessions: Vec<&Session> = loaded.program.sessions.iter().collect();
        to_value(&progression_rate(
            &sessions,
            &args.exercise_name,
            &loaded.program.meta.program_start(),
            reference,
        ))
    }

    pub async fn drift(&self, arguments: Map<String, Value>) -> Result<Value, Error> {
        let args: ExerciseArgs = args::parse(arguments)?;
        let loaded = self
            .supplied_or_loaded(&args.pk, args.program, args.sessions, Scope::Stored)
            .await?;
        let sessions: Vec<&Session> = loaded.program.sessions.iter().collect();
        to_value(&rpe_drift(
            &sessions,
            &args.exercise_name,
            &loaded.program.meta.program_start(),
            args.window_weeks,
            &loaded.program.phases,
        ))
    }

    pub async fn suggest_multipliers(&self, arguments: Map<String, Value>) -> Result<Value, Error> {
        let args: SuggestArgs = args::parse(arguments)?;
        let reference = self.reference(args.reference_date.as_deref(), None);
        let loaded = self
            .supplied_or_loaded(&args.pk, args.program, None, Scope::Stored)
            .await?;
        let sessions: Vec<&Session> = loaded.program.sessions.iter().collect();
        let history = args.max_history.unwrap_or_default();
        to_value(&multiplier_suggestions(
            &loaded.program,
            &sessions,
            &history,
            reference,
        ))
    }
}
