from app.schemas.document import DocumentResponse
from app.schemas.recommendation import EligibilityDetail, RecommendationMatch, RecommendationResponse, RuleResult, ScholarshipEligibilityResponse
from app.schemas.scholarship import ScholarshipCreate, ScholarshipResponse
from app.schemas.student_profile import StudentProfileCreate, StudentProfileResponse, StudentProfileUpdate

__all__ = [
    "StudentProfileCreate",
    "StudentProfileUpdate",
    "StudentProfileResponse",
    "ScholarshipCreate",
    "ScholarshipResponse",
    "RecommendationMatch",
    "RecommendationResponse",
    "EligibilityDetail",
    "RuleResult",
    "ScholarshipEligibilityResponse",
    "DocumentResponse",
]
