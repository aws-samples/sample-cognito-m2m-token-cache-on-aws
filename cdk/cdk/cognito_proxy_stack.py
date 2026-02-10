from aws_cdk import (
    Stack,
    CfnOutput,
    Duration,
    aws_apigateway as apigw,
)
from constructs import Construct


class CognitoProxyStack(Stack):
    """
    CDK Stack for Cognito OAuth2 Token Proxy with API Gateway Caching.
    
    This stack creates an API Gateway proxy in front of AWS Cognito's OAuth2 token endpoint,
    adding intelligent caching and API key-based access control.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        cognito_domain: str,
        stage_name: str = "dev",
        cache_ttl_seconds: int = 3600,
        cache_size_gb: str = "0.5",
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Validate cache size
        valid_cache_sizes = ["0.5", "1.6", "6.1", "13.5", "28.4", "58.2", "118", "237"]
        if cache_size_gb not in valid_cache_sizes:
            raise ValueError(f"cache_size_gb must be one of {valid_cache_sizes}")

        # Create API Gateway REST API
        api = apigw.RestApi(
            self,
            "CognitoProxy",
            rest_api_name="CognitoAuthProxy",
            description="Proxy to Cognito OAuth2 token endpoint with caching",
            endpoint_types=[apigw.EndpointType.REGIONAL],
            deploy=False,  # We'll create a custom deployment
        )

        # Create API Key
        api_key = apigw.ApiKey(
            self,
            "ProxyAPIKey",
            api_key_name=f"{construct_id}-cognito-proxy-key",
            description="API Key for Cognito proxy WAF validation",
            enabled=True,
        )

        # Create /oauth2/token resource path
        oauth2_resource = api.root.add_resource("oauth2")
        token_resource = oauth2_resource.add_resource("token")

        # VTL request template for transforming requests
        request_template = """#if($input.params().header.containsKey("Authorization"))
#set($context.requestOverride.header.Authorization = $input.params().header.get("Authorization"))
#set($body = $input.body)
#set($pairs = $body.split("&"))
#set($hasScope = false)
#set($scopeValue = "")
#foreach($pair in $pairs)
#set($kv = $pair.split("="))
#if($kv[0] == "scope")
#set($hasScope = true)
#if($kv.size() > 1)
#set($scopeValue = $kv[1])
#end
#end
#end
#if($hasScope)
grant_type=client_credentials&scope=$scopeValue
#else
grant_type=client_credentials&scope=
#end
#elseif($input.params().querystring.containsKey("client_id") && $input.params().querystring.containsKey("client_secret"))
#set($clientId = $input.params().querystring.get("client_id"))
#set($clientSecret = $input.params().querystring.get("client_secret"))
#set($credentials = "$clientId:$clientSecret")
#set($encodedCreds = $util.base64Encode($credentials))
#set($context.requestOverride.header.Authorization = "Basic $encodedCreds")
#if($input.params().querystring.containsKey("scope"))
grant_type=client_credentials&scope=$input.params().querystring.get("scope")
#else
grant_type=client_credentials&scope=
#end
#else
#set($body = $input.body)
#set($pairs = $body.split("&"))
#set($clientId = "")
#set($clientSecret = "")
#set($hasScope = false)
#set($scopeValue = "")
#foreach($pair in $pairs)
#set($kv = $pair.split("="))
#if($kv[0] == "client_id")
#set($clientId = $kv[1])
#end
#if($kv[0] == "client_secret")
#set($clientSecret = $kv[1])
#end
#if($kv[0] == "scope")
#set($hasScope = true)
#if($kv.size() > 1)
#set($scopeValue = $kv[1])
#end
#end
#end
#if($clientId && $clientSecret)
#set($credentials = "$clientId:$clientSecret")
#set($encodedCreds = $util.base64Encode($credentials))
#set($context.requestOverride.header.Authorization = "Basic $encodedCreds")
#end
#if($hasScope)
grant_type=client_credentials&scope=$scopeValue
#else
grant_type=client_credentials&scope=
#end
#end
#set($context.requestOverride.header.Accept = "application/json")"""

        # Create HTTP integration to Cognito
        integration = apigw.HttpIntegration(
            f"https://{cognito_domain}/oauth2/token",
            http_method="POST",
            options=apigw.IntegrationOptions(
                passthrough_behavior=apigw.PassthroughBehavior.WHEN_NO_TEMPLATES,
                cache_namespace=token_resource.node.id,
                cache_key_parameters=["integration.request.header.Authorization"],
                request_parameters={
                    "integration.request.header.Authorization": "method.request.header.Authorization",
                    "integration.request.header.X-API-Key": "context.identity.apiKey",
                },
                request_templates={
                    "application/x-www-form-urlencoded": request_template
                },
                integration_responses=[
                    apigw.IntegrationResponse(
                        status_code="200",
                    )
                ],
            ),
        )

        # Add POST method to /oauth2/token
        token_resource.add_method(
            "POST",
            integration,
            api_key_required=True,
            request_parameters={
                "method.request.header.Authorization": False,
                "method.request.header.Accept": False,
            },
            method_responses=[
                apigw.MethodResponse(
                    status_code="200",
                    response_models={
                        "application/json": apigw.Model.EMPTY_MODEL,
                    },
                )
            ],
        )

        # Create deployment
        deployment = apigw.Deployment(
            self,
            "ApiGatewayDeployment",
            api=api,
            description="Deployment for Cognito OAuth2 Token Proxy",
        )

        # Create stage with caching
        stage = apigw.Stage(
            self,
            "ApiGatewayStage",
            deployment=deployment,
            stage_name=stage_name,
            cache_cluster_enabled=True,
            cache_cluster_size=cache_size_gb,
            method_options={
                "/*/*": apigw.MethodDeploymentOptions(
                    caching_enabled=False,
                ),
                "/oauth2/token/POST": apigw.MethodDeploymentOptions(
                    caching_enabled=True,
                    cache_ttl=Duration.seconds(cache_ttl_seconds),
                    cache_data_encrypted=True,
                ),
            },
        )

        # Create usage plan and link API key
        usage_plan = apigw.UsagePlan(
            self,
            "ProxyUsagePlan",
            name=f"{construct_id}-cognito-proxy-plan",
            description="Usage plan for Cognito proxy",
            api_stages=[
                apigw.UsagePlanPerApiStage(
                    api=api,
                    stage=stage,
                )
            ],
        )

        usage_plan.add_api_key(api_key)

        # Outputs
        CfnOutput(
            self,
            "ApiEndpointOutput",
            description="API Gateway endpoint URL for the OAuth2 token proxy",
            value=f"https://{api.rest_api_id}.execute-api.{self.region}.amazonaws.com/{stage_name}/oauth2/token",
        )

        CfnOutput(
            self,
            "ProxyAPIKeyOutput",
            description="API Key for WAF validation (use this in WAF rules)",
            value=api_key.key_id,
        )

        CfnOutput(
            self,
            "CacheClusterSizeOutput",
            description="Cache cluster size",
            value=cache_size_gb,
        )

        CfnOutput(
            self,
            "CacheTtlOutput",
            description="Cache TTL in seconds",
            value=str(cache_ttl_seconds),
        )
