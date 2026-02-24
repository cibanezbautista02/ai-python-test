from fastapi import FastAPI
import uuid
import requests
import os
from fastapi import HTTPException, status
from record import RequestInputBody, ResponseOutputBody, NotificationStatus, RequestProcessingBody, StatusResponse
import config
import re
import json
from system_prompt import system_prompt
import httpx
from config import API_KEY

app = FastAPI(title="Notification Service (Technical Test)")

bbdd_path = "storage/bbdd.json"
bbdd = {}
PROVIDER_URL = "http://localhost:3001"
headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

client_shared = httpx.AsyncClient(timeout=30.0, limits=httpx.Limits(max_connections=500))

#Funciones auxiliares
def send_to_bbdd():
    """Escribe el estado completo de forma segura (sobrescribiendo)"""
    try:
        with open(bbdd_path, "w") as f:
            json.dump(bbdd, f, indent=4)
    except Exception:
        pass

def payload_builder(system_message: str, user_message: str):
    """Función para construir el payload que se enviará al proveedor
    Esto es para simular la construcción del payload antes de enviarlo al proveedor"""
    return {
        "messages": [
            {
                "role": "system",
                "content": system_message
            },
            {
                "role": "user",
                "content": user_message
            }
        ]
    }

def clean_llm_response(raw_response: str) -> dict:
    """Guardrails: Limpia y parsea la respuesta de la IA
     manejando primero extrae el contenido entre llaves(json)
     , seguido del parseo a diccionario, junto con la validacion
     al objeto deseado."""
    try:
        match = re.search(r"(\{.*\})", raw_response, re.DOTALL)
        if not match:
            raise ValueError("No se encontró un JSON válido en la respuesta de la IA.")
    
        clean_text = match.group(1)
        data = json.loads(clean_text)
        validated_data = RequestProcessingBody(**data)
        return validated_data.dict()
    except json.JSONDecodeError:
        raise ValueError("El motor de IA no devolvió un JSON válido.")

#endopoints
@app.post("/v1/requests", status_code=status.HTTP_201_CREATED) 
async def request_notification(body: RequestInputBody):
    """En este endpoint registramos la notificación
    y almacenamos en la base de datos simulada (bbdd) 
    con un id único generado por uuid4.
    Además tomamos el 201 como código de respuesta para 
    indicar que se ha creado correctamente."""

    notification_id = str(uuid.uuid4())
    if notification_id in bbdd and body != None:
        raise HTTPException(status_code=400, detail="Notification already exists")

    bbdd[notification_id] = {
        "id": notification_id,
        "user_input": body.user_input,
        "status": NotificationStatus.queued
    }

    send_to_bbdd()

    return ResponseOutputBody(id=notification_id)

@app.post("/v1/requests/{id}/process")
async def async_process_notification(id: str):

    if id not in bbdd:
        raise HTTPException(status_code=404, detail="Notification not found")

    content_request = bbdd[id]

    if content_request is None or content_request["status"] != NotificationStatus.queued:
        raise HTTPException(status_code=400, detail="Notification is not in a queued state")
    
    bbdd[id]["status"] = NotificationStatus.processing

    try:
        payload = payload_builder(system_message=system_prompt, user_message=bbdd[id]["user_input"])
        response = await client_shared.post(f"{PROVIDER_URL}/v1/ai/extract", json=payload, headers=headers)
        if response.status_code != 200:
            bbdd[id]["status"] = NotificationStatus.failed
            raise HTTPException(status_code=500, detail="Error processing notification")

        response_data = response.json()
        raw_content = response_data.get("choices", [{}])[0].get("message", {}).get("content") or response_data.get("content", "")
        cleaned_data = clean_llm_response(raw_content)

        if cleaned_data is None:
            bbdd[id]["status"] = NotificationStatus.failed
            raise HTTPException(status_code=500, detail="Error processing notification")
        
        notification_payload = await client_shared.post(f"{PROVIDER_URL}/v1/notify", json=cleaned_data, headers=headers)
        notification_payload.raise_for_status()

        bbdd[id]["status"] = NotificationStatus.sent
        send_to_bbdd()
        return {"message": "Notification processed and sent successfully"}
    except Exception as e:
        bbdd[id]["status"] = NotificationStatus.failed
        raise HTTPException(status_code=500, detail="Error processing notification")



@app.get("/v1/requests/{id}", status_code=status.HTTP_200_OK)
async def get_notification(id: str):
    """En este endpoint obtenemos el estado de la notificación"""

    if id not in bbdd:
        raise HTTPException(status_code=404, detail="Notification not found")

    return StatusResponse(id=id, status=bbdd[id]["status"])

"""Debido a la respuesta tardia de la IA
no llegamos a recibir la totalidad de las respuestas correctas,
podriamos devolver primero el mensaje de que se ha recibido correctamente
pero estariamos engañando al resultado realmente.
Ya que la respuesta de la IA es tardía por naturaleza"""