from pydantic import BaseModel
from enum import Enum

class NotificationType(str, Enum):
    email = "email"
    sms = "sms"

class NotificationStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    sent = "sent"
    failed = "failed"

"""Clases para enpoint numero 1,Ingesta de intenciones"""

class RequestInputBody(BaseModel):
    user_input: str

class ResponseOutputBody(BaseModel):
    id: str

"""Clases para enpoint numero 2,Procesamiento de envio"""

class RequestProcessingBody(BaseModel):
    to: str
    message: str
    type: NotificationType

"""Clases para enpoint numero 3, Consulta de estado"""

class StatusResponse(BaseModel):
    id: str
    status: NotificationStatus