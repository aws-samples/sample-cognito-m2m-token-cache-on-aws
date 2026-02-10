#!/usr/bin/env python3
import os
import aws_cdk as cdk
from cdk.cognito_proxy_stack import CognitoProxyStack


app = cdk.App()

# Get configuration from context or environment variables
cognito_domain = app.node.try_get_context("cognito_domain")
stage_name = app.node.try_get_context("stage_name") or "dev"
cache_ttl_seconds = int(app.node.try_get_context("cache_ttl_seconds") or 3600)
cache_size_gb = app.node.try_get_context("cache_size_gb") or "0.5"

# Validate required parameters
if not cognito_domain:
    raise ValueError(
        "cognito_domain is required. "
        "Provide it via context: cdk deploy -c cognito_domain=your-domain.auth.region.amazoncognito.com"
    )

CognitoProxyStack(
    app,
    "CognitoProxyStack",
    cognito_domain=cognito_domain,
    stage_name=stage_name,
    cache_ttl_seconds=cache_ttl_seconds,
    cache_size_gb=cache_size_gb,
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=os.getenv("CDK_DEFAULT_REGION"),
    ),
    description="Cognito OAuth2 Token Proxy with API Gateway Caching",
)

app.synth()
