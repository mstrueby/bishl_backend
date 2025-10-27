from datetime import datetime

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from pydantic_core import core_schema

from utils import prevent_empty_str


class PyObjectId(ObjectId):

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):

        def validate_object_id(value: str) -> ObjectId:
            if isinstance(value, ObjectId):
                return value
            if not ObjectId.is_valid(value):
                raise ValueError("Invalid ObjectId")
            return ObjectId(value)

        return core_schema.with_info_plain_validator_function(
            validate_object_id,
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: str(x), return_schema=core_schema.str_schema()
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(cls, schema, handler):
        return {"type": "string", "format": "objectid"}


class MongoBaseModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True, arbitrary_types_allowed=True, json_encoders={ObjectId: str}
    )

    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")


class User(BaseModel):
    userId: str = Field(...)
    firstName: str = Field(...)
    lastName: str = Field(...)

    @field_validator("userId", "firstName", "lastName", mode="before")
    @classmethod
    def validate_null_strings(cls, v, info):
        return prevent_empty_str(v, info.field_name)


class DocumentBase(MongoBaseModel):
    title: str = Field(...)
    alias: str = Field(...)
    category: str | None = None
    url: HttpUrl = Field(...)
    publicId: str = Field(...)
    fileName: str = Field(...)
    fileType: str = Field(...)
    fileSizeByte: int = Field(...)
    published: bool = False


class DocumentDB(DocumentBase):
    createDate: datetime | None = None
    createUser: User = Field(...)
    updateDate: datetime | None = None
    updateUser: User | None = None


class DocumentUpdate(MongoBaseModel):
    title: str | None = None
    alias: str | None = None
    category: str | None = None
    url: HttpUrl | None = None
    publicId: str | None = None
    filename: str | None = None
    fileType: str | None = None
    fileSizeByte: int | None = None
    published: bool | None = None
