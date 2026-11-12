use serde_json::{Map, Value};

use crate::engine::Engine;
use crate::error::Error;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Handler {
    AnalysisSection,
    WeeklyAnalysis,
    Progression,
    RpeDrift,
    SuggestMultipliers,
    Manifest,
    SectionsQueue,
    SectionsGet,
    SectionsInvalidate,
    Weekly,
    Bundle,
    Regenerate,
    BlocksList,
    BlocksGet,
    BlocksRegenerate,
    Compare,
    Lifetime,
}

impl Handler {
    pub fn for_operation(name: &str) -> Option<Self> {
        Some(match name {
            "analysis_section" => Self::AnalysisSection,
            "weekly_analysis" => Self::WeeklyAnalysis,
            "analyze_progression" => Self::Progression,
            "analyze_rpe_drift" => Self::RpeDrift,
            "health_suggest_e1rm_multipliers" => Self::SuggestMultipliers,
            "analytics.manifest" => Self::Manifest,
            "analytics.sections_queue" => Self::SectionsQueue,
            "analytics.sections_get" => Self::SectionsGet,
            "analytics.sections_invalidate" => Self::SectionsInvalidate,
            "analytics.weekly" => Self::Weekly,
            "analytics.bundle" => Self::Bundle,
            "analytics.regenerate" => Self::Regenerate,
            "analytics.blocks_list" => Self::BlocksList,
            "analytics.blocks_get" => Self::BlocksGet,
            "analytics.blocks_regenerate" => Self::BlocksRegenerate,
            "analytics.compare" => Self::Compare,
            "analytics.lifetime" => Self::Lifetime,
            _ => return None,
        })
    }
}

impl Engine {
    pub async fn run(
        &self,
        handler: Handler,
        arguments: Map<String, Value>,
        person: &str,
    ) -> Result<Value, Error> {
        match handler {
            Handler::AnalysisSection => self.analysis_section(arguments).await,
            Handler::WeeklyAnalysis => self.weekly_analysis(arguments).await,
            Handler::Progression => self.progression(arguments).await,
            Handler::RpeDrift => self.drift(arguments).await,
            Handler::SuggestMultipliers => self.suggest_multipliers(arguments).await,
            Handler::Manifest => self.manifest(arguments).await,
            Handler::SectionsQueue => self.sections_queue(arguments).await,
            Handler::SectionsGet => self.sections_get(arguments).await,
            Handler::SectionsInvalidate => self.sections_invalidate(arguments).await,
            Handler::Weekly => self.weekly(arguments).await,
            Handler::Bundle => self.bundle(arguments).await,
            Handler::Regenerate => self.regenerate(arguments).await,
            Handler::BlocksList => self.blocks_list(arguments).await,
            Handler::BlocksGet => self.blocks_get(arguments).await,
            Handler::BlocksRegenerate => self.blocks_regenerate(arguments, person).await,
            Handler::Compare => self.compare_blocks(arguments).await,
            Handler::Lifetime => self.lifetime_report(arguments).await,
        }
    }
}

#[cfg(test)]
mod tests {
    use crate::operations::Registry;

    #[test]
    fn every_operation_in_the_contract_has_a_handler() {
        let registry = Registry::load().expect("contract loads");
        let mut count = 0;
        for operation in registry.iter() {
            count += 1;
            assert!(
                super::Handler::for_operation(&operation.name).is_some(),
                "{} has no handler",
                operation.name
            );
        }
        assert!(count >= 17);
    }
}
