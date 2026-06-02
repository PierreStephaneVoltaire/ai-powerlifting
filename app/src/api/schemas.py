
from typing import List, Optional, Dict, Any, Literal, Union
from pydantic import BaseModel, Field
from datetime import datetime

class Model(BaseModel):

    id: str
    object: Literal["model"] = "model"
    created: int = Field(default_factory=lambda: int(datetime.now().timestamp()))
    owned_by: str = "if-prototype"

class ModelList(BaseModel):

    object: Literal["list"] = "list"
    data: List[Model]

class ChatCompletionMessage(BaseModel):

    role: Literal["system", "user", "assistant", "tool"]
    content: Optional[Union[str, List[Dict[str, Any]]]] = None
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None

class ChatCompletionRequest(BaseModel):

    model: str
    messages: List[ChatCompletionMessage]
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    n: Optional[int] = None
    stream: Optional[bool] = False
    stop: Optional[Union[str, List[str]]] = None
    max_tokens: Optional[int] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    logit_bias: Optional[Dict[str, float]] = None
    user: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    chat_id: Optional[str] = None

class ChatCompletionChoice(BaseModel):

    index: int
    message: ChatCompletionMessage
    finish_reason: Optional[str] = None

class Usage(BaseModel):

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class Attachment(BaseModel):

    filename: str
    content_type: str
    url: str

class ChatCompletionResponse(BaseModel):

    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int = Field(default_factory=lambda: int(datetime.now().timestamp()))
    model: str
    choices: List[ChatCompletionChoice]
    usage: Optional[Usage] = None
    attachments: Optional[List[Attachment]] = None

class ChatCompletionChunkDelta(BaseModel):

    role: Optional[str] = None
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None

class ChatCompletionChunkChoice(BaseModel):

    index: int
    delta: ChatCompletionChunkDelta
    finish_reason: Optional[str] = None

class ChatCompletionChunk(BaseModel):

    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(datetime.now().timestamp()))
    model: str
    choices: List[ChatCompletionChunkChoice]

class ErrorDetail(BaseModel):

    type: str
    code: Optional[str] = None
    message: str
    param: Optional[str] = None

class ErrorResponse(BaseModel):

    error: ErrorDetail
