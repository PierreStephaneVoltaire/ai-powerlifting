import os
AWS_REGION = os.getenv("AWS_REGION", "ca-central-1")
ANALYSIS_CACHE_TABLE_NAME = os.getenv("ANALYSIS_CACHE_TABLE_NAME", "if-powerlifting-analysis-cache")
