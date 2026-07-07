import os

AWS_REGION = os.getenv("AWS_REGION", "ca-central-1")
POWERLIFTING_USER_COMPETITIONS_TABLE = os.getenv(
    "POWERLIFTING_USER_COMPETITIONS_TABLE", "if-powerlifting-user-competitions"
)
POWERLIFTING_MASTER_COMPETITIONS_TABLE = os.getenv(
    "POWERLIFTING_MASTER_COMPETITIONS_TABLE", "if-powerlifting-master-competitions"
)
HEALTH_PROGRAM_PK = os.getenv("HEALTH_PROGRAM_PK", "operator")
