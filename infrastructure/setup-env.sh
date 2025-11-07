#!/bin/bash

# Setup script for CDK environment variables
# This script helps configure the required environment variables for CDK deployment

echo "🔧 Setting up CDK environment variables..."

# Get current AWS account ID and region
CURRENT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
CURRENT_REGION=$(aws configure get region 2>/dev/null || echo "us-east-1")

if [ -z "$CURRENT_ACCOUNT" ]; then
    echo "❌ Error: Unable to get AWS account ID. Please ensure you're authenticated with AWS CLI."
    echo "   Run: aws configure or aws sso login"
    exit 1
fi

echo "✅ Current AWS Account: $CURRENT_ACCOUNT"
echo "✅ Current AWS Region: $CURRENT_REGION"

# Export environment variables
export CDK_DEFAULT_ACCOUNT=$CURRENT_ACCOUNT
export CDK_DEFAULT_REGION=$CURRENT_REGION

echo ""
echo "🚀 Environment variables set:"
echo "   CDK_DEFAULT_ACCOUNT=$CDK_DEFAULT_ACCOUNT"
echo "   CDK_DEFAULT_REGION=$CDK_DEFAULT_REGION"
echo ""
echo "💡 To make these permanent, add to your shell profile:"
echo "   echo 'export CDK_DEFAULT_ACCOUNT=$CURRENT_ACCOUNT' >> ~/.zshrc"
echo "   echo 'export CDK_DEFAULT_REGION=$CURRENT_REGION' >> ~/.zshrc"
echo ""
echo "🔍 You can now run CDK commands:"
echo "   npm run build"
echo "   npm run security-scan"
echo "   cdk synth"
echo "   cdk deploy"