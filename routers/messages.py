# filename: routers/messages.py

from typing import List
from fastapi import APIRouter, Request, status, HTTPException, Path, Body, Depends
from fastapi.responses import JSONResponse, Response
from models.messages import MessageBase, MessageDB, MessageUpdate
from fastapi.encoders import jsonable_encoder
from authentication import AuthHandler, TokenPayload
from datetime import datetime

router = APIRouter()
auth = AuthHandler()

# Send a message
@router.post('/', response_description="Send a message", response_model=MessageDB)
async def send_message(
  request: Request,
  message: MessageBase = Body(...),
  token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
  user_id = token_payload.sub
  message_data = jsonable_encoder(message)
  message_data["sender_id"] = user_id
  message_data["timestamp"] = datetime.utcnow()

  result = await request.app.mongodb['messages'].insert_one(message_data)
  if result.inserted_id:
    new_message = await request.app.mongodb['messages'].find_one({"_id": result.inserted_id})
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=jsonable_encoder(MessageDB(**new_message)))

  raise HTTPException(status_code=500, detail="Message could not be sent")

# Retrieve messages for a user - Inbox
@router.get('/', response_description="List messages for a user", response_model=List[MessageDB])
async def get_messages(
  request: Request,
  token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
  user_id = token_payload.sub
  messages = await request.app.mongodb['messages'].find({"receiver_id": user_id}).sort("timestamp", -1).to_list(length=100)
  return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(messages))

# Delete a message
@router.delete('/{message_id}', response_description="Delete a message")
async def delete_message(
  request: Request,
  message_id: str = Path(..., description="The ID of the message to delete"),
  token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
  # get sender_id from message_id
  message = await request.app.mongodb['messages'].find_one({"_id":
                                message_id})
  if message is None:
    raise HTTPException(status_code=404, detail="Message not found")
  sender_id = message["sender_id"]
  if token_payload.sub != sender_id:
    raise HTTPException(status_code=403, detail="Not authorized")
  
  delete_result = await request.app.mongodb['messages'].delete_one({"_id": message_id})

  if delete_result.deleted_count == 1:
    return Response(status_code=status.HTTP_204_NO_CONTENT)

  raise HTTPException(status_code=404, detail="Message not found or you do not have permission to delete this message")

# Retrieve chat with a specific user
@router.get('/chats/{other_user_id}', response_description="Get chat with a specific user", response_model=List[MessageDB])
async def get_chat_with_user(
  request: Request,
  other_user_id: str = Path(..., description="The ID of the other user"),
  token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
  user_id = token_payload.sub
  messages = await request.app.mongodb['messages'].find({
    "$or": [
      {"sender_id": user_id, "receiver_id": other_user_id},
      {"sender_id": other_user_id, "receiver_id": user_id}
    ]
  }).sort("timestamp", -1).to_list(length=100)
  return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(messages))

# Retrieve all users that the logged-in user has chatted with
@router.get('/chats', response_description="Get users chatted with", response_model=List[str])
async def get_chatted_users(
  request: Request,
  token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
  user_id = token_payload.sub
  sent_messages = await request.app.mongodb['messages'].distinct("receiver_id", {"sender_id": user_id})
  received_messages = await request.app.mongodb['messages'].distinct("sender_id", {"receiver_id": user_id})
  chatted_users = list(set(sent_messages + received_messages))
  return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(chatted_users))

# Delete chat with a specific user
@router.delete('/chats/{other_user_id}', response_description="Delete chat with a specific user")
async def delete_chat_with_user(
  request: Request,
  other_user_id: str = Path(..., description="The ID of the other user to delete chat with"),
  token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
  user_id = token_payload.sub

  delete_result = await request.app.mongodb['messages'].delete_many({
    "$or": [
      {"sender_id": user_id, "receiver_id": other_user_id},
      {"sender_id": other_user_id, "receiver_id": user_id}
    ]
  })

  if delete_result.deleted_count > 0:
    return Response(status_code=status.HTTP_204_NO_CONTENT)

  raise HTTPException(status_code=404, detail="No messages found for this chat")