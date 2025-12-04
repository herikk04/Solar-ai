import os
import cv2
import numpy as np
import base64
import torch # <--- IMPORTANTE: Adicione isso
from flask import Flask, request, jsonify
from ultralytics import YOLO

app = Flask(__name__)

# --- Carrega o modelo UMA VEZ na inicialização ---
MODEL_PATH = "segment_thermal_panel_v01.pt" 

# 1. Instancia o modelo
model = YOLO(MODEL_PATH)

# 2. Seleção Inteligente de Hardware (A Mágica)
device = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f"--> INICIALIZANDO MODELO EM: {device.upper()} <--") # Isso vai aparecer no log do Google

# 3. Move o modelo para o hardware correto
model.to(device)

def segment_and_crop_at_point(image, point_x, point_y, model, conf_threshold=0.25, padding=10):
    """
    Segmenta, recorta e CLASSIFICA o painel no ponto X,Y.
    """
    height, width = image.shape[:2]
    
    # Validação básica de coordenadas
    if not (0 <= point_x < width and 0 <= point_y < height):
        return None, None, None, None, None, "Erro: Fora da Imagem"
    
    # Inferência
    results = model(image, conf=conf_threshold, verbose=False)
    
    if len(results) == 0 or results[0].masks is None:
        return None, None, None, None, None, "Nao Encontrado"
    
    result = results[0]
    masks = result.masks.data.cpu().numpy()
    boxes = result.boxes.xyxy.cpu().numpy()
    confidences = result.boxes.conf.cpu().numpy()
    classes = result.boxes.cls.cpu().numpy() # <--- Pega as classes (0 ou 1)
    
    # Redimensionar máscaras para o tamanho original da imagem
    masks_resized = []
    for mask in masks:
        # Usar INTER_CUBIC para melhor qualidade
        mask_resized = cv2.resize(mask, (width, height), interpolation=cv2.INTER_CUBIC)
        mask_resized = (mask_resized > 0.5).astype(np.uint8)
        masks_resized.append(mask_resized)
    
    # Encontrar qual objeto contém o ponto (x,y)
    target_idx = None
    for idx, mask in enumerate(masks_resized):
        if mask[point_y, point_x] > 0:
            target_idx = idx
            break
    
    if target_idx is None:
        return None, None, None, None, None, "Nao Encontrado"
    
    # --- LÓGICA DE CLASSIFICAÇÃO ---
    target_class_id = int(classes[target_idx]) # Pega o ID (0 ou 1)
    
    # Ajuste aqui se o seu modelo usar IDs diferentes
    if target_class_id == 1:
        status_label = "Defeito"
    else:
        status_label = "Normal"

    # --- LÓGICA DE RECORTE E ROTAÇÃO ---
    target_mask = masks_resized[target_idx]
    target_bbox = boxes[target_idx].astype(int)
    target_conf = confidences[target_idx]
    
    contours, _ = cv2.findContours(target_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rotated_crop = None
    
    if len(contours) > 0:
        main_contour = max(contours, key=cv2.contourArea)
        rect = cv2.minAreaRect(main_contour)
        box_points = cv2.boxPoints(rect)
        box_points = np.intp(box_points)
        
        # Preenche a máscara para ficar limpa
        target_mask = np.zeros_like(target_mask)
        cv2.fillPoly(target_mask, [box_points], 1)
        
        center, size, angle = rect
        width_rect, height_rect = size
        width_rect += (2 * padding)
        height_rect += (2 * padding)
        
        # Garante orientação correta
        if width_rect < height_rect:
            width_rect, height_rect = height_rect, width_rect
            angle += 90
        
        # Rotaciona a imagem para alinhar o painel
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated_full = cv2.warpAffine(image, M, (width, height), flags=cv2.INTER_LINEAR)
        
        # Recorta
        x_center, y_center = center
        x_start = int(x_center - width_rect / 2)
        y_start = int(y_center - height_rect / 2)
        x_end = int(x_center + width_rect / 2)
        y_end = int(y_center + height_rect / 2)
        
        # Limites seguros
        x_start = max(0, x_start)
        y_start = max(0, y_start)
        x_end = min(width, x_end)
        y_end = min(height, y_end)
        
        rotated_crop = rotated_full[y_start:y_end, x_start:x_end]
        
        # Bbox atualizado (apenas referência)
        x_coords = box_points[:, 0]
        y_coords = box_points[:, 1]
        x1 = max(0, int(x_coords.min() - padding))
        y1 = max(0, int(y_coords.min() - padding))
        x2 = min(width, int(x_coords.max() + padding))
        y2 = min(height, int(y_coords.max() + padding))
    else:
        # Fallback se não achar contorno
        x1, y1, x2, y2 = target_bbox
        x1, y1, x2, y2 = max(0, x1-padding), max(0, y1-padding), min(width, x2+padding), min(height, y2+padding)

    crop_image = image[y1:y2, x1:x2].copy()
    crop_mask = target_mask[y1:y2, x1:x2].copy()
    
    return crop_image, crop_mask, (x1, y1, x2, y2), target_conf, rotated_crop, status_label

@app.route('/health', methods=['GET'])
def health_check():
    return "OK", 200

@app.route('/predict', methods=['POST'])
def predict():
    try:
        data = request.json
        instances = data.get("instances", [])
        
        results = []
        
        for instance in instances:
            b64_string = instance["image_b64"]
            px = instance["point_x"]
            py = instance["point_y"]
            
            img_bytes = base64.b64decode(b64_string)
            nparr = np.frombuffer(img_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            # Chama a função
            crop, _, bbox, conf, rotated, status_model = segment_and_crop_at_point(
                image, px, py, model, padding=10
            )
            
            if crop is None:
                results.append({"found": False, "status_model": "Nao Encontrado"})
            else:
                _, buffer = cv2.imencode('.jpg', crop)
                crop_b64 = base64.b64encode(buffer).decode('utf-8')
                
                results.append({
                    "found": True,
                    "confidence": float(conf),
                    "bbox": [int(b) for b in bbox],
                    "crop_b64": crop_b64,
                    "status_model": status_model # Retorna "Defeito" ou "Normal"
                })

        return jsonify({"predictions": results})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # O Vertex AI exige porta 8080
    app.run(host='0.0.0.0', port=8080)