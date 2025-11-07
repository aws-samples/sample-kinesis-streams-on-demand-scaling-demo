import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as iam from 'aws-cdk-lib/aws-iam';

import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as stepfunctions from 'aws-cdk-lib/aws-stepfunctions';
import * as sfnTasks from 'aws-cdk-lib/aws-stepfunctions-tasks';

import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';

import { Construct } from 'constructs';
import * as path from 'path';
import { addSecuritySuppressions } from './security-suppressions';

export interface KinesisOnDemandDemoStackProps extends cdk.StackProps {
  environment: string;
}

export class KinesisOnDemandDemoStack extends cdk.Stack {
  // Note: Kinesis stream created by demo-manager.sh, not CDK
  // public readonly kinesisStream: kinesis.Stream;
  public readonly ecsCluster: ecs.Cluster;
  public readonly ecsService: ecs.FargateService;
  public readonly stepFunctionsStateMachine: stepfunctions.StateMachine;

  public readonly dashboard: cloudwatch.CfnDashboard;

  constructor(scope: Construct, id: string, props: KinesisOnDemandDemoStackProps) {
    super(scope, id, props);

    const { environment } = props;

    // Use default VPC for ECS deployment
    const vpc = this.createVpc();

    // Note: Kinesis stream will be created by demo-manager.sh
    // this.kinesisStream = this.createKinesisStream(environment);

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



    // Create CloudWatch Dashboard
    this.dashboard = this.createCloudWatchDashboard(environment);

    // Create CloudWatch Log Groups with retention policies
    this.createLogGroups(environment);

    // Output important resource information
    this.createOutputs(environment);

    // Apply security suppressions
    addSecuritySuppressions(this);
  }



  private createVpc(): ec2.IVpc {
    // Use the default VPC to avoid VPC limits
    return ec2.Vpc.fromLookup(this, 'DemoVpc', {
      isDefault: true,
    });
  }

  // Kinesis stream creation moved to demo-manager.sh
  // private createKinesisStream(environment: string): kinesis.Stream {
  //   return new kinesis.Stream(this, 'SocialMediaStream', {
  //     streamName: `social-media-stream-${environment}`,
  //     retentionPeriod: cdk.Duration.hours(24),
  //     encryption: kinesis.StreamEncryption.MANAGED,
  //     // Use On-Demand capacity mode for automatic scaling
  //     streamMode: kinesis.StreamMode.ON_DEMAND,
  //   });
  // }

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
            { phase_number: 1, target_tps: 10000, duration_seconds: 600 },
            { phase_number: 2, target_tps: 100000, duration_seconds: 1200 },
            { phase_number: 3, target_tps: 500000, duration_seconds: 1200 },
            { phase_number: 4, target_tps: 10000, duration_seconds: 600 },
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

  private createOutputs(environment: string) {
    new cdk.CfnOutput(this, 'KinesisStreamName', {
      value: `social-media-stream-${environment}`,
      description: 'Name of the Kinesis Data Stream (created by demo-manager.sh)',
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



    new cdk.CfnOutput(this, 'DashboardUrl', {
      value: `https://${this.region}.console.aws.amazon.com/cloudwatch/home?region=${this.region}#dashboards:name=${this.dashboard.dashboardName}`,
      description: 'CloudWatch Dashboard URL',
      exportName: `${this.stackName}-DashboardUrl`,
    });

    new cdk.CfnOutput(this, 'StepFunctionsConsoleUrl', {
      value: `https://${this.region}.console.aws.amazon.com/states/home?region=${this.region}#/statemachines/view/${this.stepFunctionsStateMachine.stateMachineArn}`,
      description: 'Step Functions console URL',
      exportName: `${this.stackName}-StepFunctionsConsoleUrl`,
    });
  }
}