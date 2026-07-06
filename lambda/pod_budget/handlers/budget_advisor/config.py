import os
AWS_REGION = os.getenv("AWS_REGION", "ca-central-1")
IF_HEALTH_TABLE_NAME = os.getenv("IF_HEALTH_TABLE_NAME", "if-health")
HEALTH_PROGRAM_PK = os.getenv("HEALTH_PROGRAM_PK", "operator")