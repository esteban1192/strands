#!/bin/bash

# Test script for chat functionality
AGENT_ID="70e6ae81-8333-4f05-b31f-d2068c4f3be5"
API_URL="http://localhost:8000"

echo "=== Testing Chat Functionality ==="
echo ""

# Step 1: Get agent details
echo "1. Getting agent details..."
AGENT_RESPONSE=$(curl -s -X GET "${API_URL}/api/agents/${AGENT_ID}")
echo "Agent Response: ${AGENT_RESPONSE}"
echo ""

# Step 2: Create a new chat
echo "2. Creating a new chat..."
CREATE_CHAT_RESPONSE=$(curl -s -X POST "${API_URL}/api/agents/${AGENT_ID}/chats" \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Chat"}')
echo "Create Chat Response: ${CREATE_CHAT_RESPONSE}"
CHAT_ID=$(echo $CREATE_CHAT_RESPONSE | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
echo "Chat ID: ${CHAT_ID}"
echo ""

# Step 3: Send a message
echo "3. Sending message 'Hello, what tools do you have?'..."
SEND_MESSAGE_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "${API_URL}/api/chats/${CHAT_ID}/messages" \
  -H "Content-Type: application/json" \
  -d '{"content": "Hello, what tools do you have?"}')
echo "Send Message Response: ${SEND_MESSAGE_RESPONSE}"
HTTP_CODE=$(echo "$SEND_MESSAGE_RESPONSE" | grep "HTTP_CODE:" | cut -d':' -f2)
echo "HTTP Status Code: ${HTTP_CODE}"
echo ""

# Step 4: Check SSE endpoint
echo "4. Testing SSE connection (listening for 30 seconds)..."
echo "SSE URL: ${API_URL}/api/chats/${CHAT_ID}/stream"
timeout 30 curl -s -N "${API_URL}/api/chats/${CHAT_ID}/stream" | head -50
echo ""
echo ""

# Step 5: Get chat messages
echo "5. Getting chat messages..."
sleep 5
MESSAGES_RESPONSE=$(curl -s -X GET "${API_URL}/api/chats/${CHAT_ID}/messages")
echo "Messages Response: ${MESSAGES_RESPONSE}"
echo ""

echo "=== Test Complete ==="
