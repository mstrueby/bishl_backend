# filename: routers/messages.py

from typing import List
from fastapi import APIRouter, Request, status, HTTPException, Path, Body, Depends
from fastapi.responses import JSONResponse, Response
from models.messages import MessageBase, MessageDB, MessageUpdate
from fastapi.encoders import jsonable_encoder
from authentication import AuthHandler, TokenPayload
from datetime import datetime
from exceptions import (
    ResourceNotFoundException,
    DatabaseOperationException,
    AuthorizationException
)
from logging_config import logger

router = APIRouter()
auth = AuthHandler()

# Send a message
@router.post('/',
             response_description="Send a message",
             response_model=MessageDB)
async def send_message(
    request: Request,
    message: MessageBase = Body(...),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
  mongodb = request.app.state.mongodb
  message_data = jsonable_encoder(message)
  message_data["timestamp"] = datetime.now()
  message_data["sender"] = {}
  message_data["sender"]["userId"] = token_payload.sub
  message_data["sender"]["firstName"] = token_payload.firstName
  message_data["sender"]["lastName"] = token_payload.lastName
  # get firstName and lastName of receiver
  receiver = await mongodb["users"].find_one(
    {"_id": message_data["receiverId"]})
  if not receiver:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                        detail="Receiver not found")
  message_data["receiver"] = {}
  message_data["receiver"]["userId"] = message_data["receiverId"]
  message_data["receiver"]["firstName"] = receiver["firstName"]
  message_data["receiver"]["lastName"] = receiver["lastName"]
  del message_data["receiverId"]

  result = await mongodb['messages'].insert_one(message_data)
  if result.inserted_id:
    new_message = await mongodb['messages'].find_one(
      {"_id": result.inserted_id})
    return JSONResponse(status_code=status.HTTP_201_CREATED,
                        content=jsonable_encoder(MessageDB(**new_message)))

  raise HTTPException(status_code=500, detail="Message could not be sent")


# Retrieve messages for a user - Inbox
@router.get('/',
            response_description="List messages for a user",
            response_model=List[MessageDB])
async def get_messages(
    request: Request,
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
  mongodb = request.app.state.mongodb
  user_id = token_payload.sub
  messages = await mongodb['messages'].find({
    "receiver.userId":
    user_id
  }).sort("timestamp", -1).to_list(length=100)
  #update message and set read to true
  for message in messages:
    if not message.get("read",
                       False):  # Default to False if 'read' field is missing
      await mongodb['messages'].update_one(
        {"_id": message["_id"]}, {"$set": {
          "read": True
        }})
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(messages))


# Delete a message
@router.delete('/{message_id}', response_description="Delete a message")
async def delete_message(
    request: Request,
    message_id: str = Path(..., description="The ID of the message to delete"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
  mongodb = request.app.state.mongodb
  # get sender_id from message_id
  message = await mongodb['messages'].find_one({"_id": message_id})
  if message is None:
    raise HTTPException(status_code=404, detail=f"Message with id {message_id} not found")
  sender_id = message["sender"]["userId"]
  if token_payload.sub != sender_id:
    raise HTTPException(status_code=403, detail="Nicht authorisiert")

  delete_result = await mongodb['messages'].delete_one(
    {"_id": message_id})

  if delete_result.deleted_count == 1:
    return Response(status_code=status.HTTP_204_NO_CONTENT)

  raise HTTPException(
    status_code=404,
    detail=
    "Message not found or you do not have permission to delete this message")


# Retrieve chat with a specific user
@router.get('/chats/{other_user_id}',
            response_description="Get chat with a specific user",
            response_model=List[MessageDB])
async def get_chat_with_user(
    request: Request,
    other_user_id: str = Path(..., description="The ID of the other user"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
  mongodb = request.app.state.mongodb
  user_id = token_payload.sub
  #print("user_id", user_id)
  #print("other_user_id", other_user_id)
  messages = await mongodb['messages'].find({
    "$or": [{
      "sender.userId": user_id,
      "receiver.userId": other_user_id
    }, {
      "sender.userId": other_user_id,
      "receiver.userId": user_id
    }]
  }).sort("timestamp", -1).to_list(length=100)
  #update message and set read to true
  for message in messages:
    if message["receiver"]["userId"] == user_id and not message.get(
        "read", False):  # Default to False if 'read' field is missing
      await mongodb['messages'].update_one(
        {"_id": message["_id"]}, {"$set": {
          "read": True
        }})
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(messages))


# Retrieve all users that the logged-in user has chatted with
@router.get('/chats',
            response_description="Get users chatted with",
            response_model=List[dict])
async def get_chatted_users(
    request: Request,
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
  mongodb = request.app.state.mongodb
  user_id = token_payload.sub
  sent_message_user_ids = await mongodb['messages'].distinct(
    "receiver.userId", {"sender.userId": user_id})
  received_message_user_ids = await mongodb['messages'].distinct(
    "sender.userId", {"receiver.userId": user_id})
  chatted_user_ids = list(
    set(sent_message_user_ids + received_message_user_ids))
  chatted_users = []
  for chat_user_id in chatted_user_ids:
    chat_user = await mongodb['users'].find_one(
      {"_id": chat_user_id}, {
        "firstName": 1,
        "lastName": 1
      })
    if chat_user:
      unread_count = 0
      unread_count = await mongodb['messages'].count_documents({
        "sender.userId":
        chat_user_id,
        "receiver.userId":
        user_id,
        "read":
        False
      })
      chatted_users.append({
        "userId": chat_user_id,
        "firstName": chat_user["firstName"],
        "lastName": chat_user["lastName"],
        "unreadCount": unread_count
      })
  return JSONResponse(status_code=status.HTTP_200_OK, content=chatted_users)
