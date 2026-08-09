"""Abstract risk model interface."""

from abc import ABC, abstractmethod

from backend.app.database.schemas.risk import RiskFeatures, RiskPredictionSchema


class BaseRiskModel(ABC):
    """Contract for future rule-based or ML-based risk predictors."""

    @abstractmethod
    def predict(self, features: RiskFeatures) -> RiskPredictionSchema:
        """Generate a support-risk prediction."""

