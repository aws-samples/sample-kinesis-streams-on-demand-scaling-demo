#!/bin/bash

# Script to list Kinesis stream shards with detailed formatting
# Usage: ./list-shards.sh [stream-name] [environment]
# Default: social-media-stream-production

STREAM_NAME=${1:-"social-media-stream-production"}
ENVIRONMENT=${2:-"production"}

echo "=== Kinesis Stream: $STREAM_NAME ==="
echo

# Get total shard count
TOTAL_SHARDS=$(aws kinesis list-shards --stream-name "$STREAM_NAME" --query 'length(Shards)' --output text 2>/dev/null)

if [ $? -ne 0 ]; then
    echo "Error: Could not access stream '$STREAM_NAME'"
    echo "Make sure the stream exists and you have proper AWS credentials configured."
    exit 1
fi

echo "Total Shards: $TOTAL_SHARDS"
echo

# Get shard details with status
echo "Shard Details:"
aws kinesis list-shards --stream-name "$STREAM_NAME" \
    --query 'Shards[*].{ShardId:ShardId,ParentShardId:ParentShardId||`ROOT`,Status:SequenceNumberRange.EndingSequenceNumber&&`CLOSED`||`OPEN`}' \
    --output table

echo
echo "Legend:"
echo "  - OPEN: Active shard currently accepting records"
echo "  - CLOSED: Shard that has been split or merged (no longer accepting records)"
echo "  - ROOT: Original shard with no parent"