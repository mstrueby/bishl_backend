
from bson import ObjectId
from pydantic import Field, BaseModel, field_validator, HttpUrl, ConfigDict
from pydantic_core import core_schema
from typing import Optional
from datetime import datetime
from utils import prevent_empty_str


class PyObjectId(ObjectId):

  @classmethod
  def __get_pydantic_core_schema__(cls, source_type, handler):
    return core_schema.no_info_plain_validator_function(
      cls.validate,
      serialization=core_schema.plain_serializer_function_ser_schema(
        lambda x: str(x)
      )
    )

  @classmethod
  def validate(cls, v):
    if isinstance(v, ObjectId):
      return v
    if not ObjectId.is_valid(v):
      raise ValueError("Invalid objectid")
    return ObjectId(v)


class MongoBaseModel(BaseModel):
  model_config = ConfigDict(
    populate_by_name=True,
    arbitrary_types_allowed=True,
    json_encoders={ObjectId: str}
  )
  
  id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")


class User(BaseModel):
  userId: str = Field(...)
  firstName: str = Field(...)
  lastName: str = Field(...)

  @field_validator('userId', 'firstName', 'lastName', mode='before')
  @classmethod
  def validate_null_strings(cls, v, info):
    return prevent_empty_str(v, info.field_name)


class DocumentBase(MongoBaseModel):
  title: str = Field(...)
  alias: str = Field(...)
  category: Optional[str] = None
  url: HttpUrl = Field(...)
  publicId: str = Field(...)
  fileName: str = Field(...)
  fileType: str = Field(...)
  fileSizeByte: int = Field(...)
  published: bool = False


class DocumentDB(DocumentBase):
  createDate: Optional[datetime] = None
  createUser: User = Field(...)
  updateDate: Optional[datetime] = None
  updateUser: Optional[User] = None


class DocumentUpdate(MongoBaseModel):
  title: Optional[str] = None
  alias: Optional[str] = None
  category: Optional[str] = None
  url: Optional[HttpUrl] = None
  publicId: Optional[str] = None
  filename: Optional[str] = None
  fileType: Optional[str] = None
  fileSizeByte: Optional[int] = None
  published: Optional[bool] = None
