from aws_cdk import (
    Stack,
    CfnOutput,
    Duration,
    CustomResource,
    RemovalPolicy,
    aws_apigateway as apigw,
    aws_wafv2 as wafv2,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_logs as logs,
    custom_resources as cr,
)
from constructs import Construct
import base64


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
        cognito_user_pool_arn: str = None,
        stage_name: str = "dev",
        cache_ttl_seconds: int = 3600,
        cache_size_gb: str = "0.5",
        enable_waf_protection: bool = True,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Validate cache size
        valid_cache_sizes = ["0.5", "1.6", "6.1", "13.5", "28.4", "58.2", "118", "237"]
        if cache_size_gb not in valid_cache_sizes:
            raise ValueError(f"cache_size_gb must be one of {valid_cache_sizes}")

        if enable_waf_protection and not cognito_user_pool_arn:
            raise ValueError("cognito_user_pool_arn is required when WAF protection is enabled")

        # Create CloudWatch Log Group for API Gateway access logs
        access_log_group = logs.LogGroup(
            self,
            "ApiGatewayAccessLogs",
            log_group_name=f"/aws/apigateway/{construct_id}-access-logs",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Create API Gateway REST API
        api = apigw.RestApi(
            self,
            "CognitoProxy",
            rest_api_name="CognitoAuthProxy",
            description="Proxy to Cognito OAuth2 token endpoint with caching",
            endpoint_types=[apigw.EndpointType.REGIONAL],
            deploy=False,  # We'll create a custom deployment
        )

        # Create API Key (CDK will generate the value)
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
                    "integration.request.header.x-api-key": "method.request.header.x-api-key",
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
                "method.request.header.x-api-key": True,
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

        # Create stage with caching and logging
        stage = apigw.Stage(
            self,
            "ApiGatewayStage",
            deployment=deployment,
            stage_name=stage_name,
            cache_cluster_enabled=True,
            cache_cluster_size=cache_size_gb,
            access_log_destination=apigw.LogGroupLogDestination(access_log_group),
            access_log_format=apigw.AccessLogFormat.json_with_standard_fields(
                caller=True,
                http_method=True,
                ip=True,
                protocol=True,
                request_time=True,
                resource_path=True,
                response_length=True,
                status=True,
                user=True,
            ),
            logging_level=apigw.MethodLoggingLevel.INFO,
            data_trace_enabled=True,
            metrics_enabled=True,
            method_options={
                "/*/*": apigw.MethodDeploymentOptions(
                    caching_enabled=False,
                    logging_level=apigw.MethodLoggingLevel.INFO,
                    data_trace_enabled=True,
                    metrics_enabled=True,
                ),
                "/oauth2/token/POST": apigw.MethodDeploymentOptions(
                    caching_enabled=True,
                    cache_ttl=Duration.seconds(cache_ttl_seconds),
                    cache_data_encrypted=True,
                    logging_level=apigw.MethodLoggingLevel.INFO,
                    data_trace_enabled=True,
                    metrics_enabled=True,
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

        # Create WAF WebACL to protect Cognito User Pool
        if enable_waf_protection:
            # Create Lambda function to retrieve API key value
            get_api_key_lambda = lambda_.Function(
                self,
                "GetApiKeyFunction",
                runtime=lambda_.Runtime.PYTHON_3_12,
                handler="index.handler",
                code=lambda_.Code.from_inline("""
import boto3
import json

apigateway = boto3.client('apigateway')

def handler(event, context):
    request_type = event['RequestType']
    
    if request_type == 'Create' or request_type == 'Update':
        api_key_id = event['ResourceProperties']['ApiKeyId']
        
        try:
            response = apigateway.get_api_key(
                apiKey=api_key_id,
                includeValue=True
            )
            api_key_value = response['value']
            
            return {
                'PhysicalResourceId': api_key_id,
                'Data': {
                    'ApiKeyValue': api_key_value
                }
            }
        except Exception as e:
            raise Exception(f"Failed to get API key: {str(e)}")
    
    elif request_type == 'Delete':
        return {
            'PhysicalResourceId': event['PhysicalResourceId']
        }
"""),
                timeout=Duration.seconds(30),
            )

            # Grant permissions to read API keys
            get_api_key_lambda.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["apigateway:GET"],
                    resources=[
                        f"arn:aws:apigateway:{self.region}::/apikeys/{api_key.key_id}"
                    ],
                )
            )

            # Create custom resource to get API key value
            api_key_provider = cr.Provider(
                self,
                "ApiKeyProvider",
                on_event_handler=get_api_key_lambda,
            )

            api_key_custom_resource = CustomResource(
                self,
                "ApiKeyCustomResource",
                service_token=api_key_provider.service_token,
                properties={
                    "ApiKeyId": api_key.key_id,
                },
            )

            # Get the API key value from custom resource
            api_key_value = api_key_custom_resource.get_att_string("ApiKeyValue")

            # Base64 encode the API key value for WAF matching
            # Note: We can't base64 encode at synth time since it's a token
            # The WAF will need to match the plain text value
            
            web_acl = wafv2.CfnWebACL(
                self,
                "CognitoProtectionWebACL",
                scope="REGIONAL",
                default_action=wafv2.CfnWebACL.DefaultActionProperty(
                    block=wafv2.CfnWebACL.BlockActionProperty(
                        custom_response=wafv2.CfnWebACL.CustomResponseProperty(
                            response_code=403,
                            custom_response_body_key="CognitoDenied"
                        )
                    )
                ),
                visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                    cloud_watch_metrics_enabled=True,
                    metric_name="CognitoProtectionWebACL",
                    sampled_requests_enabled=True
                ),
                rules=[
                    wafv2.CfnWebACL.RuleProperty(
                        name="allow-api-key-requests",
                        priority=0,
                        statement=wafv2.CfnWebACL.StatementProperty(
                            byte_match_statement=wafv2.CfnWebACL.ByteMatchStatementProperty(
                                search_string=api_key_value,
                                field_to_match=wafv2.CfnWebACL.FieldToMatchProperty(
                                    single_header={"Name": "x-api-key"}
                                ),
                                text_transformations=[
                                    wafv2.CfnWebACL.TextTransformationProperty(
                                        priority=0,
                                        type="NONE"
                                    )
                                ],
                                positional_constraint="EXACTLY"
                            )
                        ),
                        action=wafv2.CfnWebACL.RuleActionProperty(
                            allow={}
                        ),
                        visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                            cloud_watch_metrics_enabled=True,
                            metric_name="allow-api-key-requests",
                            sampled_requests_enabled=True
                        )
                    )
                ],
                custom_response_bodies={
                    "CognitoDenied": wafv2.CfnWebACL.CustomResponseBodyProperty(
                        content_type="APPLICATION_JSON",
                        content='{"message":"WAF is preventing direct access to Cognito. Please use the API Gateway endpoint with a valid API key."}'
                    )
                }
            )

            # Ensure WAF is created after we get the API key value
            web_acl.node.add_dependency(api_key_custom_resource)

            # Associate WAF with Cognito User Pool
            wafv2.CfnWebACLAssociation(
                self,
                "CognitoWAFAssociation",
                resource_arn=cognito_user_pool_arn,
                web_acl_arn=web_acl.attr_arn
            )

            CfnOutput(
                self,
                "WebACLOutput",
                description="WAF WebACL protecting Cognito User Pool",
                value=web_acl.attr_arn,
            )

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
