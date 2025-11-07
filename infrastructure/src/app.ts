#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { AwsSolutionsChecks, NagSuppressions } from 'cdk-nag';
import { KinesisOnDemandDemoStack } from './kinesis-ondemand-demo-stack';
import { addSecuritySuppressions } from './security-suppressions';

const app = new cdk.App();

// Get environment configuration
const environment = app.node.tryGetContext('environment') || 'production';
const region = app.node.tryGetContext('region') || process.env.CDK_DEFAULT_REGION;
const account = app.node.tryGetContext('account') || process.env.CDK_DEFAULT_ACCOUNT;

// Stack configuration
const stackName = `kinesis-ondemand-demo-${environment}`;

const stack = new KinesisOnDemandDemoStack(app, stackName, {
  env: {
    account: account,
    region: region,
  },
  environment: environment,
  description: `Kinesis On-Demand Demo Infrastructure - ${environment}`,
  tags: {
    Project: 'KinesisOnDemandDemo',
    Environment: environment,
    ManagedBy: 'CDK'
  }
});

// Add security suppressions for acceptable risks
addSecuritySuppressions(stack);

// Add cdk-nag security checks
cdk.Aspects.of(app).add(new AwsSolutionsChecks({ verbose: true }));