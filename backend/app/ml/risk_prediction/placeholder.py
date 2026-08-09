"""Placeholder risk model implementation."""

from backend.app.database.schemas.risk import RiskFeatures, RiskLevel, RiskPredictionSchema
from backend.app.ml.risk_prediction.interface import BaseRiskModel


class PlaceholderRiskModel(BaseRiskModel):
    """Safe default implementation that makes non-production behavior explicit."""

    def predict(self, features: RiskFeatures) -> RiskPredictionSchema:
        return RiskPredictionSchema(
            case_id=0,
            risk_level=RiskLevel.LOW,
            risk_score=0.0,
            contributing_factors=["Risk model not implemented"],
            recommended_intervention="Manual review required until prediction logic is added.",
        )

