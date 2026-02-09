import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as kinesis from 'aws-cdk-lib/aws-kinesis';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as stepfunctions from 'aws-cdk-lib/aws-stepfunctions';
import * as sfnTasks from 'aws-cdk-lib/aws-stepfunctions-tasks';

import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import { NagSuppressions } from 'cdk-nag';

import { Construct } from 'constructs';
import * as path from 'path';
import { addSecuritySuppressions } from './security-suppressions';

export interface KinesisOnDemandDemoStackProps extends cdk.StackProps {
  environment: string;
}

export class KinesisOnDemandDemoStack extends cdk.Stack {
  public readonly kinesisStream: kinesis.Stream;
  public readonly ecsCluster: ecs.Cluster;
  public readonly ecsService: ecs.FargateService;
  public readonly stepFunctionsStateMachine: stepfunctions.StateMachine;

  public readonly dashboard: cloudwatch.CfnDashboard;
  public readonly sentimentDashboard: cloudwatch.CfnDashboard;

  constructor(scope: Construct, id: string, props: KinesisOnDemandDemoStackProps) {
    super(scope, id, props);

    const { environment } = props;

    // Use default VPC for ECS deployment
    const vpc = this.createVpc();

    // Create Kinesis stream in CDK (demo-manager.sh can delete/recreate it later)
    this.kinesisStream = this.createKinesisStream(environment);

    // Create ECS Cluster and related resources
    const { cluster, service, taskDefinition } = this.createEcsResources(vpc, environment);
    this.ecsCluster = cluster;
    this.ecsService = service;

    // Create Lambda functions for message processing and cost calculation
    const { messageProcessorFunction, costCalculatorFunction } = this.createLambdaFunctions(environment);

    // Create Step Functions controller and state machine
    const { controllerFunction, stateMachine } = this.createStepFunctionsResources(
      cluster,
      service,
      environment
    );
    this.stepFunctionsStateMachine = stateMachine;



    // Create Sentiment Analysis Consumer Lambda
    const sentimentConsumerFunction = this.createSentimentAnalysisConsumer(environment);

    // Create CloudWatch Dashboard
    this.dashboard = this.createCloudWatchDashboard(environment);
    
    // Create Sentiment Analysis Dashboard
    this.sentimentDashboard = this.createSentimentAnalysisDashboard(environment);

    // Create CloudWatch Log Groups with retention policies
    this.createLogGroups(environment);

    // Output important resource information
    this.createOutputs(environment, sentimentConsumerFunction);

    // Apply security suppressions
    addSecuritySuppressions(this);
  }



  private createVpc(): ec2.IVpc {
    // Use the default VPC to avoid VPC limits
    return ec2.Vpc.fromLookup(this, 'DemoVpc', {
      isDefault: true,
    });
  }

  private createKinesisStream(environment: string): kinesis.Stream {
    // Create Kinesis stream with On-Demand capacity mode
    // Note: demo-manager.sh can delete and recreate this stream to reset shard count
    return new kinesis.Stream(this, 'SocialMediaStream', {
      streamName: `social-media-stream-${environment}`,
      retentionPeriod: cdk.Duration.hours(24),
      encryption: kinesis.StreamEncryption.MANAGED,
      // Use On-Demand capacity mode for automatic scaling
      streamMode: kinesis.StreamMode.ON_DEMAND,
    });
  }

  private createEcsResources(vpc: ec2.IVpc, environment: string) {
    // Create ECS Cluster
    const cluster = new ecs.Cluster(this, 'DemoCluster', {
      clusterName: `kinesis-demo-${environment}`,
      vpc: vpc,
      containerInsights: true,
    });

    // Create task execution role
    const taskExecutionRole = new iam.Role(this, 'EcsTaskExecutionRole', {
      roleName: `KinesisDemo-ECSTaskExecutionRole-${environment}`,
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AmazonECSTaskExecutionRolePolicy'),
      ],
      inlinePolicies: {
        ECRAccess: new iam.PolicyDocument({
          statements: [
            // ECR authorization token requires wildcard resource
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: ['ecr:GetAuthorizationToken'],
              resources: ['*'],
            }),
            // ECR repository access can be scoped to specific repositories
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'ecr:BatchCheckLayerAvailability',
                'ecr:GetDownloadUrlForLayer',
                'ecr:BatchGetImage',
              ],
              resources: [
                `arn:aws:ecr:${this.region}:${this.account}:repository/kinesis-ondemand-demo*`,
                `arn:aws:ecr:${this.region}:${this.account}:repository/cdk-*`,
              ],
            }),
          ],
        }),
        CloudWatchLogs: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'logs:CreateLogGroup',
                'logs:CreateLogStream',
                'logs:PutLogEvents',
              ],
              resources: [`arn:aws:logs:${this.region}:${this.account}:log-group:/ecs/kinesis-ondemand-demo*`],
            }),
          ],
        }),
      },
    });

    // Create task role
    const taskRole = new iam.Role(this, 'EcsTaskRole', {
      roleName: `KinesisDemo-ECSTaskRole-${environment}`,
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      inlinePolicies: {
        KinesisProducerPolicy: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'kinesis:PutRecord',
                'kinesis:PutRecords',
                'kinesis:DescribeStream',
                'kinesis:ListStreams',
              ],
              resources: [`arn:aws:kinesis:${this.region}:${this.account}:stream/social-media-stream-${environment}`],
            }),
          ],
        }),
        CloudWatchMetricsPolicy: new iam.PolicyDocument({
          statements: [
            // CloudWatch PutMetricData requires wildcard resource but is restricted by namespace condition
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: ['cloudwatch:PutMetricData'],
              resources: ['*'],
              conditions: {
                StringLike: {
                  'cloudwatch:namespace': [
                    `KinesisOnDemandDemo/${environment}`,
                    'KinesisOnDemandDemo',
                    'KinesisOnDemandDemo/*',
                  ],
                },
              },
            }),
          ],
        }),
      },
    });

    // Create task definition
    const taskDefinition = new ecs.FargateTaskDefinition(this, 'DataGeneratorTaskDef', {
      family: `kinesis-ondemand-demo-${environment}`,
      cpu: 1024,
      memoryLimitMiB: 2048,
      executionRole: taskExecutionRole,
      taskRole: taskRole,
    });

    // Add container to task definition
    const container = taskDefinition.addContainer('kinesis-data-generator', {
      image: ecs.ContainerImage.fromAsset(path.join(__dirname, '../../'), {
        exclude: ['infrastructure/**', '.git/**', '.vscode/**', 'docs/**', 'examples/**']
      }),
      essential: true,
      environment: {
        AWS_REGION: this.region,
        STREAM_NAME: `social-media-stream-${environment}`,
        TARGET_TPS: '5000',
        DEMO_PHASE: '1',
        CLOUDWATCH_NAMESPACE: `KinesisOnDemandDemo/${environment}`,
        ENVIRONMENT: environment,
        METRICS_PUBLISH_INTERVAL: '30',
        ENABLE_CLOUDWATCH_METRICS: 'true',
        CONTROLLER_MODE: 'step_functions',
      },
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: 'ecs',
        logGroup: new logs.LogGroup(this, 'EcsLogGroup', {
          logGroupName: '/ecs/kinesis-ondemand-demo',
          retention: logs.RetentionDays.ONE_WEEK,
        }),
      }),
      healthCheck: {
        command: ['CMD-SHELL', 'python health_check.py || exit 1'],
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(10),
        retries: 3,
        startPeriod: cdk.Duration.seconds(60),
      },
      stopTimeout: cdk.Duration.seconds(30),
    });

    container.addPortMappings({
      containerPort: 8080,
      protocol: ecs.Protocol.TCP,
    });

    // Create ECS service
    const service = new ecs.FargateService(this, 'DataGeneratorService', {
      serviceName: `kinesis-ondemand-demo-${environment}`,
      cluster: cluster,
      taskDefinition: taskDefinition,
      desiredCount: 0, // Start with 0 tasks, demo-manager.sh will set to the desired count
      platformVersion: ecs.FargatePlatformVersion.LATEST,
      enableExecuteCommand: true,
      propagateTags: ecs.PropagatedTagSource.SERVICE,
      assignPublicIp: true, // Required for default VPC public subnets
      vpcSubnets: {
        subnetType: ec2.SubnetType.PUBLIC,
      },
    });

    // Note: Auto-scaling is managed by Step Functions based on demo phases
    // No CPU-based auto-scaling needed as task count is controlled programmatically

    return { cluster, service, taskDefinition };
  }

  private createLambdaFunctions(environment: string) {
    // Create message processing Lambda function
    const messageProcessorFunction = new lambda.Function(this, 'MessageProcessorFunction', {
      functionName: `kinesis-demo-message-processor-${environment}`,
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'message_processor.lambda_handler',
      code: lambda.Code.fromInline(`
import json
import logging
import boto3
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

cloudwatch = boto3.client('cloudwatch')

def lambda_handler(event, context):
    """Process Kinesis records and publish metrics."""
    
    records_processed = 0
    total_latency = 0
    
    for record in event.get('Records', []):
        try:
            # Decode Kinesis data
            payload = json.loads(record['kinesis']['data'])
            
            # Calculate processing latency
            if 'timestamp' in payload:
                record_time = datetime.fromisoformat(payload['timestamp'])
                latency = (datetime.utcnow() - record_time).total_seconds() * 1000
                total_latency += latency
            
            records_processed += 1
            
        except Exception as e:
            logger.error(f"Error processing record: {e}")
    
    # Publish metrics
    if records_processed > 0:
        avg_latency = total_latency / records_processed
        
        cloudwatch.put_metric_data(
            Namespace='KinesisOnDemandDemo/Processing',
            MetricData=[
                {
                    'MetricName': 'RecordsProcessed',
                    'Value': records_processed,
                    'Unit': 'Count'
                },
                {
                    'MetricName': 'ProcessingLatency',
                    'Value': avg_latency,
                    'Unit': 'Milliseconds'
                }
            ]
        )
    
    return {
        'statusCode': 200,
        'recordsProcessed': records_processed
    }
      `),
      timeout: cdk.Duration.minutes(5),
      memorySize: 256,
      environment: {
        ENVIRONMENT: environment,
      },
      role: new iam.Role(this, 'MessageProcessorRole', {
        assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
        managedPolicies: [
          iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
        ],
        inlinePolicies: {
          CloudWatchMetrics: new iam.PolicyDocument({
            statements: [
              new iam.PolicyStatement({
                effect: iam.Effect.ALLOW,
                actions: ['cloudwatch:PutMetricData'],
                resources: ['*'],
              }),
            ],
          }),
          KinesisStreamAccess: new iam.PolicyDocument({
            statements: [
              new iam.PolicyStatement({
                effect: iam.Effect.ALLOW,
                actions: [
                  'kinesis:GetRecords',
                  'kinesis:GetShardIterator',
                  'kinesis:DescribeStream',
                  'kinesis:DescribeStreamSummary',
                  'kinesis:ListShards',
                  'kinesis:ListStreams',
                ],
                resources: [`arn:aws:kinesis:${this.region}:${this.account}:stream/social-media-stream-${environment}`],
              }),
            ],
          }),
        },
      }),
    });

    // Note: Kinesis event source mapping will be created when stream exists
    // messageProcessorFunction.addEventSourceMapping('KinesisEventSource', {
    //   eventSourceArn: this.kinesisStream.streamArn,
    //   batchSize: 100,
    //   startingPosition: lambda.StartingPosition.LATEST,
    //   maxBatchingWindow: cdk.Duration.seconds(5),
    // });

    // Create cost calculation Lambda function
    const costCalculatorFunction = new lambda.Function(this, 'CostCalculatorFunction', {
      functionName: `kinesis-demo-cost-calculator-${environment}`,
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'cost_calculator.lambda_handler',
      code: lambda.Code.fromInline(`
import json
import logging
import boto3
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

cloudwatch = boto3.client('cloudwatch')

def lambda_handler(event, context):
    """Calculate real-time costs for the demo."""
    
    # On-Demand pricing (example rates)
    SHARD_HOUR_COST = 0.015
    PAYLOAD_UNIT_COST = 0.014 / 1000000  # per million payload units
    
    # Get current metrics from CloudWatch
    try:
        # This is a placeholder - implement actual cost calculation
        current_cost = 0.50  # Example cost
        
        # Publish cost metrics
        cloudwatch.put_metric_data(
            Namespace='KinesisOnDemandDemo/Cost',
            MetricData=[
                {
                    'MetricName': 'CurrentCost',
                    'Value': current_cost,
                    'Unit': 'None'
                }
            ]
        )
        
        return {
            'statusCode': 200,
            'currentCost': current_cost
        }
        
    except Exception as e:
        logger.error(f"Error calculating costs: {e}")
        return {
            'statusCode': 500,
            'error': str(e)
        }
      `),
      timeout: cdk.Duration.minutes(2),
      memorySize: 256,
      environment: {
        ENVIRONMENT: environment,
      },
      role: new iam.Role(this, 'CostCalculatorRole', {
        assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
        managedPolicies: [
          iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
        ],
        inlinePolicies: {
          CloudWatchAccess: new iam.PolicyDocument({
            statements: [
              new iam.PolicyStatement({
                effect: iam.Effect.ALLOW,
                actions: [
                  'cloudwatch:PutMetricData',
                  'cloudwatch:GetMetricStatistics',
                ],
                resources: ['*'],
              }),
            ],
          }),
        },
      }),
    });

    return { messageProcessorFunction, costCalculatorFunction };
  }

  private createStepFunctionsResources(
    cluster: ecs.Cluster,
    service: ecs.FargateService,
    environment: string
  ) {
    // Create Step Functions controller Lambda
    const controllerFunction = new lambda.Function(this, 'StepFunctionsController', {
      functionName: `kinesis-demo-stepfunctions-controller-${environment}`,
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'step_functions_controller.lambda_handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../step-functions')),
      timeout: cdk.Duration.minutes(2),
      memorySize: 256,
      environment: {
        CLUSTER_NAME: cluster.clusterName,
        SERVICE_NAME: service.serviceName,
        ENVIRONMENT: environment,
        PER_TASK_CAPACITY: '3500',
      },
      role: new iam.Role(this, 'StepFunctionsControllerRole', {
        roleName: `KinesisDemo-StepFunctionsControllerRole-${environment}`,
        assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
        managedPolicies: [
          iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
        ],
        inlinePolicies: {
          ECSControlPolicy: new iam.PolicyDocument({
            statements: [
              new iam.PolicyStatement({
                effect: iam.Effect.ALLOW,
                actions: [
                  'ecs:UpdateService',
                  'ecs:DescribeServices',
                  'ecs:DescribeClusters',
                  'ecs:DescribeTasks',
                  'ecs:ListTasks',
                  'ecs:RegisterTaskDefinition',
                ],
                resources: [
                  cluster.clusterArn,
                  service.serviceArn,
                  `arn:aws:ecs:${this.region}:${this.account}:task/${cluster.clusterName}/*`,
                  `arn:aws:ecs:${this.region}:${this.account}:task-definition/*`,
                ],
              }),
              new iam.PolicyStatement({
                effect: iam.Effect.ALLOW,
                actions: [
                  'ecs:DescribeTaskDefinition',
                ],
                resources: ['*'], // DescribeTaskDefinition requires wildcard resource
              }),
              new iam.PolicyStatement({
                effect: iam.Effect.ALLOW,
                actions: ['iam:PassRole'],
                resources: ['*'],
                conditions: {
                  StringEquals: {
                    'iam:PassedToService': 'ecs-tasks.amazonaws.com',
                  },
                },
              }),
            ],
          }),
          CloudWatchMetricsPolicy: new iam.PolicyDocument({
            statements: [
              new iam.PolicyStatement({
                effect: iam.Effect.ALLOW,
                actions: ['cloudwatch:PutMetricData'],
                resources: ['*'],
                conditions: {
                  StringLike: {
                    'cloudwatch:namespace': [
                      'KinesisOnDemandDemo/StepFunctions',
                      'KinesisOnDemandDemo/PhaseInfo',
                      'KinesisOnDemandDemo/*',
                    ],
                  },
                },
              }),
            ],
          }),
        },
      }),
    });

    // Create Step Functions state machine
    const initializeDemo = new sfnTasks.LambdaInvoke(this, 'InitializeDemo', {
      lambdaFunction: controllerFunction,
      payload: stepfunctions.TaskInput.fromObject({
        operation: 'initialize_demo',
        demo_config: {
          phases: [
            { phase_number: 1, target_tps: 10000, duration_seconds: 120 },
            { phase_number: 2, target_tps: 100000, duration_seconds: 120 },
            { phase_number: 3, target_tps: 500000, duration_seconds: 120 },
            { phase_number: 4, target_tps: 10000, duration_seconds: 120 },
          ],
        },
      }),
      resultPath: '$.demo_state',
      retryOnServiceExceptions: true,
    });

    const startPhase1 = new sfnTasks.LambdaInvoke(this, 'StartPhase1', {
      lambdaFunction: controllerFunction,
      payload: stepfunctions.TaskInput.fromObject({
        operation: 'start_phase',
        phase_number: 1,
        target_tps: 10000,
        'demo_state.$': '$.demo_state.Payload.demo_state',
      }),
      resultPath: '$.phase1_result',
      retryOnServiceExceptions: true,
    });

    const waitPhase1 = new stepfunctions.Wait(this, 'WaitPhase1Duration', {
      time: stepfunctions.WaitTime.duration(cdk.Duration.seconds(600)),
    });

    const startPhase2 = new sfnTasks.LambdaInvoke(this, 'StartPhase2', {
      lambdaFunction: controllerFunction,
      payload: stepfunctions.TaskInput.fromObject({
        operation: 'start_phase',
        phase_number: 2,
        target_tps: 100000,
        'demo_state.$': '$.phase1_result.Payload.demo_state',
      }),
      resultPath: '$.phase2_result',
      retryOnServiceExceptions: true,
    });

    const waitPhase2 = new stepfunctions.Wait(this, 'WaitPhase2Duration', {
      time: stepfunctions.WaitTime.duration(cdk.Duration.seconds(1200)),
    });

    const startPhase3 = new sfnTasks.LambdaInvoke(this, 'StartPhase3', {
      lambdaFunction: controllerFunction,
      payload: stepfunctions.TaskInput.fromObject({
        operation: 'start_phase',
        phase_number: 3,
        target_tps: 500000,
        'demo_state.$': '$.phase2_result.Payload.demo_state',
      }),
      resultPath: '$.phase3_result',
      retryOnServiceExceptions: true,
    });

    const waitPhase3 = new stepfunctions.Wait(this, 'WaitPhase3Duration', {
      time: stepfunctions.WaitTime.duration(cdk.Duration.seconds(1200)),
    });

    const startPhase4 = new sfnTasks.LambdaInvoke(this, 'StartPhase4', {
      lambdaFunction: controllerFunction,
      payload: stepfunctions.TaskInput.fromObject({
        operation: 'start_phase',
        phase_number: 4,
        target_tps: 10000,
        'demo_state.$': '$.phase3_result.Payload.demo_state',
      }),
      resultPath: '$.phase4_result',
      retryOnServiceExceptions: true,
    });

    const waitPhase4 = new stepfunctions.Wait(this, 'WaitPhase4Duration', {
      time: stepfunctions.WaitTime.duration(cdk.Duration.seconds(600)),
    });

    const cleanupDemo = new sfnTasks.LambdaInvoke(this, 'CleanupDemo', {
      lambdaFunction: controllerFunction,
      payload: stepfunctions.TaskInput.fromObject({
        operation: 'cleanup_demo',
        'demo_state.$': '$.phase4_result.Payload.demo_state',
      }),
      resultPath: '$.cleanup_result',
      retryOnServiceExceptions: true,
    });

    const demoCompleted = new stepfunctions.Pass(this, 'DemoCompleted', {
      result: stepfunctions.Result.fromObject({
        status: 'completed',
        message: 'Kinesis On-Demand Demo completed successfully',
      }),
    });

    // Define the state machine workflow
    const definition = initializeDemo
      .next(startPhase1)
      .next(waitPhase1)
      .next(startPhase2)
      .next(waitPhase2)
      .next(startPhase3)
      .next(waitPhase3)
      .next(startPhase4)
      .next(waitPhase4)
      .next(cleanupDemo)
      .next(demoCompleted);

    // Create CloudWatch Log Group for Step Functions
    const stepFunctionsLogGroup = new logs.LogGroup(this, 'StepFunctionsLogGroup', {
      logGroupName: `/aws/stepfunctions/kinesis-demo-${environment}`,
      retention: logs.RetentionDays.ONE_WEEK,
    });

    const stateMachine = new stepfunctions.StateMachine(this, 'DemoStateMachine', {
      stateMachineName: `kinesis-demo-${environment}`,
      definitionBody: stepfunctions.DefinitionBody.fromChainable(definition),
      timeout: cdk.Duration.minutes(90),
      tracingEnabled: true, // Enable X-Ray tracing
      logs: {
        destination: stepFunctionsLogGroup,
        level: stepfunctions.LogLevel.ALL,
        includeExecutionData: true,
      },
      role: new iam.Role(this, 'StepFunctionsRole', {
        roleName: `KinesisDemo-StepFunctionsRole-${environment}`,
        assumedBy: new iam.ServicePrincipal('states.amazonaws.com'),
        inlinePolicies: {
          LambdaInvokePolicy: new iam.PolicyDocument({
            statements: [
              new iam.PolicyStatement({
                effect: iam.Effect.ALLOW,
                actions: ['lambda:InvokeFunction'],
                resources: [controllerFunction.functionArn],
              }),
            ],
          }),
          CloudWatchLogsPolicy: new iam.PolicyDocument({
            statements: [
              new iam.PolicyStatement({
                effect: iam.Effect.ALLOW,
                actions: [
                  'logs:CreateLogDelivery',
                  'logs:GetLogDelivery',
                  'logs:UpdateLogDelivery',
                  'logs:DeleteLogDelivery',
                  'logs:ListLogDeliveries',
                  'logs:PutResourcePolicy',
                  'logs:DescribeResourcePolicies',
                  'logs:DescribeLogGroups',
                ],
                resources: ['*'],
              }),
            ],
          }),
          XRayTracingPolicy: new iam.PolicyDocument({
            statements: [
              new iam.PolicyStatement({
                effect: iam.Effect.ALLOW,
                actions: [
                  'xray:PutTraceSegments',
                  'xray:PutTelemetryRecords',
                  'xray:GetSamplingRules',
                  'xray:GetSamplingTargets',
                ],
                resources: ['*'],
              }),
            ],
          }),
        },
      }),
    });

    return { controllerFunction, stateMachine };
  }

  private createSentimentAnalysisConsumer(environment: string): lambda.Function {
    // Create Lambda Layer for dependencies (boto3, orjson)
    const dependenciesLayer = new lambda.LayerVersion(this, 'SentimentConsumerDependenciesLayer', {
      layerVersionName: `sentiment-consumer-dependencies-${environment}`,
      code: lambda.Code.fromAsset(path.join(__dirname, '../../lambda/sentiment-consumer/layer'), {
        bundling: {
          image: lambda.Runtime.PYTHON_3_12.bundlingImage,
          command: [
            'bash', '-c',
            'pip install -r requirements.txt -t /asset-output/python && ' +
            'rm -rf /asset-output/python/*.dist-info /asset-output/python/__pycache__'
          ],
        },
      }),
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_12],
      description: 'Dependencies for Sentiment Analysis Consumer (boto3, orjson)',
    });

    // Create Lambda execution role with required permissions
    const sentimentConsumerRole = new iam.Role(this, 'SentimentConsumerRole', {
      roleName: `KinesisDemo-SentimentConsumerRole-${environment}`,
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
      ],
      inlinePolicies: {
        KinesisStreamAccess: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'kinesis:GetRecords',
                'kinesis:GetShardIterator',
                'kinesis:DescribeStream',
                'kinesis:DescribeStreamSummary',
                'kinesis:ListShards',
              ],
              resources: [
                `arn:aws:kinesis:${this.region}:${this.account}:stream/social-media-stream-${environment}`
              ],
            }),
          ],
        }),
        BedrockAccess: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'bedrock:InvokeModel',
              ],
              resources: [
                // Allow inference profile to route to any of the three US regions
                'arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0',
                'arn:aws:bedrock:us-west-2::foundation-model/amazon.nova-lite-v1:0',
                'arn:aws:bedrock:us-east-2::foundation-model/amazon.nova-lite-v1:0',
                // Also allow inference profiles in all three regions
                'arn:aws:bedrock:us-east-1:*:inference-profile/*',
                'arn:aws:bedrock:us-west-2:*:inference-profile/*',
                'arn:aws:bedrock:us-east-2:*:inference-profile/*'
              ],
            }),
          ],
        }),
        CloudWatchLogsAccess: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'logs:CreateLogStream',
                'logs:PutLogEvents',
              ],
              resources: [
                `arn:aws:logs:${this.region}:${this.account}:log-group:/aws/lambda/sentiment-analysis-consumer-${environment}:*`,
                `arn:aws:logs:${this.region}:${this.account}:log-group:/aws/lambda/sentiment-analysis-consumer-${environment}/insights:*`
              ],
            }),
          ],
        }),
        CloudWatchMetrics: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: ['cloudwatch:PutMetricData'],
              resources: ['*'],
              conditions: {
                StringLike: {
                  'cloudwatch:namespace': ['SentimentAnalysis/*'],
                },
              },
            }),
          ],
        }),
      },
    });

    // Add CDK-nag suppression for Bedrock inference profile wildcard
    NagSuppressions.addResourceSuppressions(
      sentimentConsumerRole,
      [
        {
          id: 'AwsSolutions-IAM5',
          reason: 'Bedrock inference profiles require wildcard in account ID portion of ARN. This is scoped to inference-profile resource type in the deployment region only.',
          appliesTo: [`Resource::arn:aws:bedrock:${this.region}:*:inference-profile/*`],
        },
      ],
      true // applyToChildren
    );

    // Create Lambda function with inline code deployment
    // CDK will automatically bundle the Lambda code and shared utilities
    const sentimentConsumerFunction = new lambda.Function(this, 'SentimentConsumerFunction', {
      functionName: `sentiment-analysis-consumer-${environment}`,
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'lambda_handler.handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../'), {
        bundling: {
          image: lambda.Runtime.PYTHON_3_12.bundlingImage,
          command: [
            'bash', '-c',
            // Copy all Lambda function code
            // Note: Lambda has its own models.py and serialization.py for Lambda-specific types
            'mkdir -p /asset-output && ' +
            'cp -r /asset-input/lambda/sentiment-consumer/*.py /asset-output/ && ' +
            'cp -r /asset-input/lambda/sentiment-consumer/extractors /asset-output/ && ' +
            // Copy shared utilities from project root to shared directory
            // These are for SocialMediaPost and related types
            'mkdir -p /asset-output/shared && ' +
            'cp /asset-input/shared/models.py /asset-output/shared/ && ' +
            'cp /asset-input/shared/serialization.py /asset-output/shared/ && ' +
            // Create a minimal __init__.py for shared module (without config import)
            'echo "# Shared utilities for Lambda" > /asset-output/shared/__init__.py && ' +
            'echo "from .models import SocialMediaPost, KinesisRecord, DemoMetrics, GeoLocation, PostType" >> /asset-output/shared/__init__.py && ' +
            'echo "from .serialization import serialize_to_json, deserialize_from_json, post_from_bytes" >> /asset-output/shared/__init__.py && ' +
            // Clean up unnecessary files
            'rm -rf /asset-output/layer /asset-output/build /asset-output/dist /asset-output/__pycache__ /asset-output/*/__pycache__ && ' +
            'rm -f /asset-output/package.sh /asset-output/requirements.txt /asset-output/.gitignore /asset-output/*.md /asset-output/*.zip && ' +
            // List contents for verification
            'echo "=== Lambda package structure ===" && ' +
            'ls -la /asset-output/ | head -20'
          ],
        },
        exclude: [
          'infrastructure/**',
          '.git/**',
          'lambda/sentiment-consumer/layer/**',
          'lambda/sentiment-consumer/build/**',
          'lambda/sentiment-consumer/dist/**',
          '__pycache__/**',
          '**/__pycache__/**',
          '*.pyc',
          'package.sh',
          '.gitignore',
          '*.md',
          '*.zip',
        ],
      }),
      layers: [dependenciesLayer],
      timeout: cdk.Duration.minutes(10), // Increased for larger batches (10K records)
      memorySize: 2048, // Increased memory for processing 10K records per batch
      environment: {
        // Use inference profile ID - it will route to us-east-1, us-west-2, or us-east-2
        BEDROCK_MODEL_ID: 'us.amazon.nova-lite-v1:0',
        BEDROCK_REGION: this.region,
        LOG_GROUP_NAME: `/aws/lambda/sentiment-analysis-consumer-${environment}`,
        INSIGHTS_LOG_GROUP_NAME: `/aws/lambda/sentiment-analysis-consumer-${environment}/insights`,
        ENVIRONMENT: environment,
      },
      role: sentimentConsumerRole,
      description: 'Sentiment Analysis Consumer - Processes social media posts from Kinesis using Bedrock Nova Micro',
    });

    // Configure Event Source Mapping
    // Strategy: Lambda randomly samples 20 posts from each batch for Bedrock analysis
    // This ensures consistent, reliable Bedrock performance regardless of scale
    // High batch size (500) maintains throughput as KDS scales to more shards
    // Lambda always samples exactly 20 posts for Bedrock, ensuring consistent latency (~1-2s)
    // At 190K records/min peak with 100 shards: 190K ÷ 500 = 380 invocations/min ÷ 100 shards = 3.8 inv/min per shard
    // Total Bedrock calls: ~6-8 per minute (well under 200 req/min quota)
    sentimentConsumerFunction.addEventSourceMapping('KinesisEventSource', {
      eventSourceArn: `arn:aws:kinesis:${this.region}:${this.account}:stream/social-media-stream-${environment}`,
      batchSize: 500, // High batch size for throughput; Lambda samples 20 for Bedrock
      maxBatchingWindow: cdk.Duration.seconds(5), // Shorter window for faster processing
      startingPosition: lambda.StartingPosition.LATEST,
      reportBatchItemFailures: true,
      parallelizationFactor: 1, // Keep at 1 to minimize concurrent invocations per shard
    });

    // Create CloudWatch Log Groups
    this.createSentimentAnalysisLogGroups(environment);

    // Add resource tags
    cdk.Tags.of(sentimentConsumerFunction).add('Environment', environment);
    cdk.Tags.of(sentimentConsumerFunction).add('Component', 'SentimentAnalysisConsumer');
    cdk.Tags.of(sentimentConsumerFunction).add('CostCenter', 'KinesisOnDemandDemo');
    cdk.Tags.of(dependenciesLayer).add('Environment', environment);
    cdk.Tags.of(dependenciesLayer).add('Component', 'SentimentAnalysisConsumer');

    return sentimentConsumerFunction;
  }

  private createSentimentAnalysisLogGroups(environment: string) {
    // Main Lambda log group
    new logs.LogGroup(this, 'SentimentConsumerLogGroup', {
      logGroupName: `/aws/lambda/sentiment-analysis-consumer-${environment}`,
      retention: logs.RetentionDays.ONE_WEEK,
    });

    // Insight log streams
    const insightLogGroup = new logs.LogGroup(this, 'SentimentInsightsLogGroup', {
      logGroupName: `/aws/lambda/sentiment-analysis-consumer-${environment}/insights`,
      retention: logs.RetentionDays.ONE_WEEK,
    });

    // Create log streams
    const logStreams = [
      'product-sentiment',
      'trending-topics',
      'engagement-sentiment',
      'geographic-sentiment',
      'viral-events',
    ];

    logStreams.forEach(streamName => {
      new logs.LogStream(this, `${streamName}LogStream`, {
        logGroup: insightLogGroup,
        logStreamName: streamName,
      });
    });
  }



  private createCloudWatchDashboard(environment: string): cloudwatch.CfnDashboard {
    const streamName = `social-media-stream-${environment}`;
    const dashboardName = `kinesis-ondemand-demo-${environment}`;
    
    // Dashboard configuration embedded directly with dynamic values
    const dashboardBody = {
      widgets: [
        {
          type: "metric",
          x: 12,
          y: 6,
          width: 12,
          height: 6,
          properties: {
            metrics: [
              [
                {
                  expression: "METRICS()/60",
                  label: "Per Second:",
                  id: "e1",
                  region: this.region,
                  stat: "Sum",
                  period: 60
                }
              ],
              [
                "AWS/Kinesis",
                "PutRecords.TotalRecords",
                "StreamName",
                streamName,
                {
                  region: this.region,
                  id: "m1",
                  visible: false
                }
              ],
              [
                ".",
                "PutRecords.SuccessfulRecords",
                ".",
                ".",
                {
                  region: this.region,
                  id: "m2",
                  visible: false
                }
              ]
            ],
            view: "timeSeries",
            title: "Traffic Volume (Messages/Second)",
            region: this.region,
            period: 60,
            stat: "Sum"
          }
        },
        {
          type: "metric",
          x: 0,
          y: 6,
          width: 12,
          height: 6,
          properties: {
            view: "timeSeries",
            title: "Throttle Exceptions",
            region: this.region,
            metrics: [
              [
                "AWS/Kinesis",
                "WriteProvisionedThroughputExceeded",
                "StreamName",
                streamName,
                {
                  stat: "Sum"
                }
              ]
            ],
            yAxis: {}
          }
        },
        {
          type: "metric",
          x: 0,
          y: 0,
          width: 4,
          height: 6,
          properties: {
            metrics: [
              [
                "AWS/Kinesis",
                "PutRecords.SuccessfulRecords",
                "StreamName",
                streamName,
                {
                  region: this.region
                }
              ]
            ],
            view: "singleValue",
            title: "Total successful records",
            region: this.region,
            period: 60,
            stat: "Sum",
            setPeriodToTimeRange: true,
            sparkline: false
          }
        },
        {
          type: "metric",
          x: 4,
          y: 0,
          width: 4,
          height: 6,
          properties: {
            metrics: [
              [
                "AWS/Kinesis",
                "PutRecords.ThrottledRecords",
                "StreamName",
                streamName,
                {
                  region: this.region
                }
              ]
            ],
            view: "singleValue",
            title: "Total throttled records",
            region: this.region,
            period: 60,
            stat: "Sum",
            setPeriodToTimeRange: true,
            sparkline: false
          }
        },
        {
          type: "metric",
          x: 12,
          y: 0,
          width: 12,
          height: 6,
          properties: {
            metrics: [
              [
                {
                  expression: "METRICS() / 60",
                  label: "IncomingBytes (MB/Second)",
                  id: "e1",
                  region: this.region,
                  period: 60,
                  stat: "Sum"
                }
              ],
              [
                "AWS/Kinesis",
                "IncomingBytes",
                "StreamName",
                streamName,
                {
                  region: this.region,
                  id: "m1",
                  visible: false
                }
              ]
            ],
            view: "timeSeries",
            stacked: false,
            region: this.region,
            stat: "Sum",
            period: 60,
            title: "IncomingBytes"
          }
        },
        {
          type: "metric",
          x: 0,
          y: 12,
          width: 12,
          height: 6,
          properties: {
            metrics: [
              [
                {
                  expression: "SEARCH('{KinesisOnDemandDemo/StepFunctions,ClusterName,DemoId,ServiceName}', 'Sum', 60)",
                  id: "e1",
                  period: 60,
                  region: this.region,
                  stat: "Sum"
                }
              ]
            ],
            view: "timeSeries",
            stacked: false,
            region: this.region,
            title: "TaskCount, TotalTargetTPS",
            period: 60,
            stat: "Sum"
          }
        },
        {
          type: "metric",
          x: 8,
          y: 0,
          width: 4,
          height: 6,
          properties: {
            metrics: [
              [
                "AWS/Kinesis",
                "PutRecords.TotalRecords",
                "StreamName",
                streamName,
                {
                  region: this.region
                }
              ]
            ],
            view: "singleValue",
            stacked: false,
            region: this.region,
            period: 60,
            stat: "Average",
            title: "Batch size average",
            setPeriodToTimeRange: false,
            sparkline: false
          }
        },
        {
            type: "metric",
            x: 12,
            y: 12,
            width: 12,
            height: 6,
            properties: {
                metrics: [
                    [ "AWS/Bedrock", "Invocations", "ModelId", "amazon.nova-lite-v1:0", { "id": "m1" } ],
                    [ ".", "InvocationThrottles", ".", ".", { "id": "m2" } ]
                ],
                view: "timeSeries",
                stacked: false,
                region: this.region,
                stat: "Sum",
                period: 60,
                title: "Bedrock API Invocation"
            }
        }
      ]
    };
    
    // Create the dashboard using the CfnDashboard construct for direct JSON support
    const dashboard = new cloudwatch.CfnDashboard(this, 'DemoDashboard', {
      dashboardName: dashboardName,
      dashboardBody: JSON.stringify(dashboardBody),
    });

    return dashboard;
  }

  private createSentimentAnalysisDashboard(environment: string): cloudwatch.CfnDashboard {
    const dashboardName = `sentiment-analysis-${environment}`;
    
    const dashboardBody = {
      widgets: [
        {
          type: "metric",
          x: 0,
          y: 0,
          width: 12,
          height: 6,
          properties: {
            metrics: [
              [ "SentimentAnalysis/Insights", "PositivePosts", "Environment", environment, "DemoPhase", "0", { stat: "Sum", color: "#2ca02c" } ],
              [ "...", "NegativePosts", ".", ".", ".", ".", { stat: "Sum", color: "#d62728" } ],
              [ "...", "NeutralPosts", ".", ".", ".", ".", { stat: "Sum", color: "#7f7f7f" } ]
            ],
            view: "timeSeries",
            stacked: true,
            region: this.region,
            title: "Sentiment Distribution Over Time",
            period: 60,
            yAxis: {
              left: {
                label: "Post Count"
              }
            }
          }
        },
        {
          type: "metric",
          x: 12,
          y: 0,
          width: 6,
          height: 6,
          properties: {
            metrics: [
              [ "SentimentAnalysis/Insights", "PositivePosts", "Environment", environment, "DemoPhase", "0", { stat: "Sum", label: "Positive" } ],
              [ "...", "NegativePosts", ".", ".", ".", ".", { stat: "Sum", label: "Negative" } ],
              [ "...", "NeutralPosts", ".", ".", ".", ".", { stat: "Sum", label: "Neutral" } ]
            ],
            view: "pie",
            region: this.region,
            title: "Overall Sentiment Distribution",
            period: 3600,
            setPeriodToTimeRange: true
          }
        },
        {
          type: "metric",
          x: 18,
          y: 0,
          width: 6,
          height: 6,
          properties: {
            metrics: [
              [ "SentimentAnalysis/Insights", "AverageSentimentScore", "Environment", environment, "DemoPhase", "0", { stat: "Average" } ]
            ],
            view: "singleValue",
            region: this.region,
            title: "Average Sentiment Score",
            period: 60,
            setPeriodToTimeRange: false
          }
        },
        {
          type: "metric",
          x: 0,
          y: 6,
          width: 12,
          height: 6,
          properties: {
            metrics: [
              [ "SentimentAnalysis/Insights", "AverageSentimentScore", "Environment", environment, "DemoPhase", "0", { stat: "Average" } ]
            ],
            view: "timeSeries",
            region: this.region,
            title: "Sentiment Score Trend",
            period: 60,
            yAxis: {
              left: {
                min: -1,
                max: 1,
                label: "Sentiment Score"
              }
            },
            annotations: {
              horizontal: [
                {
                  value: 0,
                  label: "Neutral",
                  fill: "above"
                }
              ]
            }
          }
        },
        {
          type: "metric",
          x: 12,
          y: 6,
          width: 12,
          height: 6,
          properties: {
            metrics: [
              [ "SentimentAnalysis/Insights", "TrendingTopicsCount", "Environment", environment, "DemoPhase", "0", { stat: "Sum" } ]
            ],
            view: "timeSeries",
            region: this.region,
            title: "Trending Topics Count",
            period: 60,
            yAxis: {
              left: {
                label: "Count"
              }
            }
          }
        },
        {
          type: "metric",
          x: 0,
          y: 12,
          width: 12,
          height: 6,
          properties: {
            metrics: [
              [ "SentimentAnalysis/Insights", "EngagementSentimentCorrelation", "Environment", environment, "DemoPhase", "0", { stat: "Average" } ]
            ],
            view: "timeSeries",
            region: this.region,
            title: "Engagement-Sentiment Correlation",
            period: 60,
            yAxis: {
              left: {
                min: -1,
                max: 1,
                label: "Correlation"
              }
            }
          }
        },
        {
          type: "metric",
          x: 12,
          y: 12,
          width: 12,
          height: 6,
          properties: {
            metrics: [
              [ "SentimentAnalysis/Insights", "ControversialPosts", "Environment", environment, "DemoPhase", "0", { stat: "Sum" } ]
            ],
            view: "timeSeries",
            region: this.region,
            title: "Controversial Posts (High Engagement, Negative Sentiment)",
            period: 60,
            yAxis: {
              left: {
                label: "Count"
              }
            }
          }
        },
        {
          type: "metric",
          x: 0,
          y: 18,
          width: 24,
          height: 6,
          properties: {
            metrics: [
              [ { expression: "SEARCH('{SentimentAnalysis/Insights,Product} MetricName=\"ProductSentiment\"', 'Average', 300)", id: "e1" } ]
            ],
            view: "timeSeries",
            region: this.region,
            title: "Product Sentiment Scores",
            period: 60,
            yAxis: {
              left: {
                min: -1,
                max: 1,
                label: "Sentiment"
              }
            }
          }
        },
        {
          type: "metric",
          x: 0,
          y: 24,
          width: 24,
          height: 6,
          properties: {
            metrics: [
              [ { expression: "SEARCH('{SentimentAnalysis/Insights,Hashtag} MetricName=\"HashtagPostCount\"', 'Sum', 300)", id: "e1" } ]
            ],
            view: "timeSeries",
            region: this.region,
            title: "Hashtag Post Counts",
            period: 60,
            yAxis: {
              left: {
                label: "Post Count"
              }
            }
          }
        },
        {
          type: "metric",
          x: 0,
          y: 30,
          width: 24,
          height: 6,
          properties: {
            metrics: [
              [ { expression: "SEARCH('{SentimentAnalysis/Insights,City,Country} MetricName=\"GeographicSentiment\"', 'Average', 300)", id: "e1" } ]
            ],
            view: "timeSeries",
            region: this.region,
            title: "Geographic Sentiment by Location",
            period: 60,
            yAxis: {
              left: {
                min: -1,
                max: 1,
                label: "Sentiment"
              }
            }
          }
        },
        {
          type: "metric",
          x: 0,
          y: 36,
          width: 12,
          height: 6,
          properties: {
            metrics: [
              [ "AWS/Lambda", "Invocations", { stat: "Sum", label: "Lambda Invocations" } ],
              [ ".", "Errors", { stat: "Sum", label: "Errors", color: "#d62728" } ]
            ],
            view: "timeSeries",
            region: this.region,
            title: "Lambda Performance",
            period: 60
          }
        },
        {
          type: "metric",
          x: 12,
          y: 36,
          width: 12,
          height: 6,
          properties: {
            metrics: [
              [ "SentimentAnalysis/Consumer", "ErrorRate", { stat: "Average" } ],
              [ ".", "ProcessingLatency", { stat: "Average", yAxis: "right" } ]
            ],
            view: "timeSeries",
            region: this.region,
            title: "Processing Metrics",
            period: 60,
            yAxis: {
              left: {
                label: "Error Rate (%)"
              },
              right: {
                label: "Latency (ms)"
              }
            }
          }
        }
      ]
    };
    
    const dashboard = new cloudwatch.CfnDashboard(this, 'SentimentDashboard', {
      dashboardName: dashboardName,
      dashboardBody: JSON.stringify(dashboardBody),
    });

    return dashboard;
  }

  private createLogGroups(environment: string) {
    // ECS log group (already created in ECS resources)

    // Lambda log groups
    new logs.LogGroup(this, 'MessageProcessorLogGroup', {
      logGroupName: `/aws/lambda/kinesis-demo-message-processor-${environment}`,
      retention: logs.RetentionDays.ONE_WEEK,
    });

    new logs.LogGroup(this, 'CostCalculatorLogGroup', {
      logGroupName: `/aws/lambda/kinesis-demo-cost-calculator-${environment}`,
      retention: logs.RetentionDays.ONE_WEEK,
    });

    new logs.LogGroup(this, 'StepFunctionsControllerLogGroup', {
      logGroupName: `/aws/lambda/kinesis-demo-stepfunctions-controller-${environment}`,
      retention: logs.RetentionDays.ONE_WEEK,
    });

    // Step Functions log group (created in Step Functions resources)
  }

  private createOutputs(environment: string, sentimentConsumerFunction?: lambda.Function) {
    new cdk.CfnOutput(this, 'KinesisStreamName', {
      value: this.kinesisStream.streamName,
      description: 'Name of the Kinesis Data Stream',
      exportName: `${this.stackName}-KinesisStreamName`,
    });

    new cdk.CfnOutput(this, 'EcsClusterName', {
      value: this.ecsCluster.clusterName,
      description: 'Name of the ECS cluster',
      exportName: `${this.stackName}-EcsClusterName`,
    });

    new cdk.CfnOutput(this, 'EcsServiceName', {
      value: this.ecsService.serviceName,
      description: 'Name of the ECS service',
      exportName: `${this.stackName}-EcsServiceName`,
    });

    new cdk.CfnOutput(this, 'StateMachineArn', {
      value: this.stepFunctionsStateMachine.stateMachineArn,
      description: 'ARN of the Step Functions state machine',
      exportName: `${this.stackName}-StateMachineArn`,
    });

    // Sentiment Analysis Consumer outputs
    if (sentimentConsumerFunction) {
      new cdk.CfnOutput(this, 'SentimentConsumerFunctionArn', {
        value: sentimentConsumerFunction.functionArn,
        description: 'ARN of the Sentiment Analysis Consumer Lambda function',
        exportName: `${this.stackName}-SentimentConsumerFunctionArn`,
      });

      new cdk.CfnOutput(this, 'SentimentConsumerLogGroupName', {
        value: `/aws/lambda/sentiment-analysis-consumer-${environment}`,
        description: 'CloudWatch Log Group for Sentiment Analysis Consumer',
        exportName: `${this.stackName}-SentimentConsumerLogGroupName`,
      });

      new cdk.CfnOutput(this, 'SentimentInsightsLogGroupName', {
        value: `/aws/lambda/sentiment-analysis-consumer-${environment}/insights`,
        description: 'CloudWatch Log Group for Sentiment Insights',
        exportName: `${this.stackName}-SentimentInsightsLogGroupName`,
      });
    }

    new cdk.CfnOutput(this, 'DashboardUrl', {
      value: `https://${this.region}.console.aws.amazon.com/cloudwatch/home?region=${this.region}#dashboards:name=${this.dashboard.dashboardName}`,
      description: 'CloudWatch Dashboard URL',
      exportName: `${this.stackName}-DashboardUrl`,
    });
    
    new cdk.CfnOutput(this, 'SentimentDashboardUrl', {
      value: `https://${this.region}.console.aws.amazon.com/cloudwatch/home?region=${this.region}#dashboards:name=${this.sentimentDashboard.dashboardName}`,
      description: 'Sentiment Analysis Dashboard URL',
      exportName: `${this.stackName}-SentimentDashboardUrl`,
    });

    new cdk.CfnOutput(this, 'StepFunctionsConsoleUrl', {
      value: `https://${this.region}.console.aws.amazon.com/states/home?region=${this.region}#/statemachines/view/${this.stepFunctionsStateMachine.stateMachineArn}`,
      description: 'Step Functions console URL',
      exportName: `${this.stackName}-StepFunctionsConsoleUrl`,
    });
  }
}