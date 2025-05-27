#!/usr/bin/env python3
"""
Système de surveillance pour Raspberry Pi Zero 2 W
Auteur: Clément JONGHMANS
Version: 1.0
"""

import os
import pwd
import time
import threading
import signal
import sys
from datetime import datetime, timedelta
from flask import Flask, render_template_string, Response, jsonify, request
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput
import cv2
import numpy as np
from PIL import Image
import json
import logging

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SurveillanceCamera:
    def __init__(self):
        self.picam2 = None
        self.is_recording = False
        self.motion_detection_active = False
        self.last_motion_time = None
        self.recording_thread = None
        self.motion_thread = None
        
        # Configuration (détection automatique du répertoire utilisateur)
        import pwd
        username = pwd.getpwuid(os.getuid()).pw_name
        base_dir = f'/home/{username}/surveillance'
        
        self.config = {
            'video_dir': f'{base_dir}/videos',
            'photos_dir': f'{base_dir}/photos',
            'max_video_duration': 300,  # 5 minutes max par vidéo
            'motion_threshold': 1000,   # Seuil de détection de mouvement
            'cleanup_days': 7,          # Supprime les fichiers de plus de 7 jours
            'resolution': (1920, 1080), # Résolution vidéo
            'framerate': 30
        }
        
        # Création des dossiers
        os.makedirs(self.config['video_dir'], exist_ok=True)
        os.makedirs(self.config['photos_dir'], exist_ok=True)
        
        # Initialisation de la caméra
        self.init_camera()
        
        # Variables pour la détection de mouvement
        self.previous_frame = None
        self.motion_detected = False
        
    def init_camera(self):
        """Initialise la caméra Pi"""
        try:
            self.picam2 = Picamera2()
            
            # Configuration de prévisualisation
            preview_config = self.picam2.create_preview_configuration(
                main={"size": (640, 480)},
                lores={"size": (320, 240), "format": "YUV420"}
            )
            self.picam2.configure(preview_config)
            
            # Configuration vidéo pour l'enregistrement
            self.video_config = self.picam2.create_video_configuration(
                main={"size": self.config['resolution']},
                lores={"size": (320, 240), "format": "YUV420"}
            )
            
            self.picam2.start()
            time.sleep(2)
            logger.info("Caméra initialisée avec succès")
            
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation de la caméra: {e}")
            raise
    
    def generate_frames(self):
        """Générateur de frames pour le streaming"""
        while True:
            try:
                # Capture d'une frame
                frame = self.picam2.capture_array()
                
                # Conversion BGR vers RGB pour Flask
                if len(frame.shape) == 3:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                else:
                    frame_rgb = frame
                
                # Ajout d'informations sur l'image
                self.add_overlay(frame_rgb)
                
                # Encodage JPEG
                _, buffer = cv2.imencode('.jpg', frame_rgb)
                frame_bytes = buffer.tobytes()
                
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                
                time.sleep(0.1)  # Limite le framerate pour économiser les ressources
                
            except Exception as e:
                logger.error(f"Erreur lors de la génération des frames: {e}")
                break
    
    def add_overlay(self, frame):
        """Ajoute des informations sur l'image"""
        # Timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, timestamp, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Statut d'enregistrement
        if self.is_recording:
            cv2.putText(frame, "REC", (frame.shape[1] - 80, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            cv2.circle(frame, (frame.shape[1] - 100, 25), 5, (0, 0, 255), -1)
        
        # Détection de mouvement
        if self.motion_detection_active:
            status = "MOTION DETECTED" if self.motion_detected else "MONITORING"
            color = (0, 255, 0) if self.motion_detected else (255, 255, 0)
            cv2.putText(frame, status, (10, frame.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    
    def start_recording(self, duration=None):
        """Démarre l'enregistrement vidéo"""
        if self.is_recording:
            logger.warning("Enregistrement déjà en cours")
            return False
        
        try:
            # Reconfiguration pour l'enregistrement
            self.picam2.stop()
            self.picam2.configure(self.video_config)
            
            # Nom du fichier avec timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(self.config['video_dir'], f"video_{timestamp}.mp4")
            
            # Configuration de l'encodeur
            encoder = H264Encoder(bitrate=10000000)
            output = FileOutput(filename)
            
            self.picam2.start_recording(encoder, output)
            self.is_recording = True
            self.current_recording_file = filename
            
            logger.info(f"Enregistrement démarré: {filename}")
            
            # Thread pour arrêter automatiquement après la durée spécifiée
            if duration:
                self.recording_thread = threading.Thread(
                    target=self._stop_recording_after_delay,
                    args=(duration,)
                )
                self.recording_thread.start()
            
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors du démarrage de l'enregistrement: {e}")
            return False
    
    def stop_recording(self):
        """Arrête l'enregistrement vidéo"""
        if not self.is_recording:
            return False
        
        try:
            self.picam2.stop_recording()
            self.is_recording = False
            
            # Retour à la configuration de prévisualisation
            self.picam2.stop()
            preview_config = self.picam2.create_preview_configuration(
                main={"size": (640, 480)},
                lores={"size": (320, 240), "format": "YUV420"}
            )
            self.picam2.configure(preview_config)
            self.picam2.start()
            
            logger.info("Enregistrement arrêté")
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors de l'arrêt de l'enregistrement: {e}")
            return False
    
    def _stop_recording_after_delay(self, duration):
        """Arrête l'enregistrement après un délai"""
        time.sleep(duration)
        if self.is_recording:
            self.stop_recording()
    
    def take_photo(self):
        """Prend une photo"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(self.config['photos_dir'], f"photo_{timestamp}.jpg")
            
            # Capture haute résolution pour la photo
            self.picam2.capture_file(filename)
            
            logger.info(f"Photo prise: {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"Erreur lors de la prise de photo: {e}")
            return None
    
    def detect_motion(self, frame):
        """Détecte le mouvement dans une frame"""
        if self.previous_frame is None:
            self.previous_frame = frame
            return False
        
        # Conversion en niveaux de gris
        gray_current = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray_previous = cv2.cvtColor(self.previous_frame, cv2.COLOR_BGR2GRAY)
        
        # Différence entre les frames
        frame_diff = cv2.absdiff(gray_current, gray_previous)
        
        # Seuillage
        _, thresh = cv2.threshold(frame_diff, 30, 255, cv2.THRESH_BINARY)
        
        # Calcul du nombre de pixels différents
        motion_pixels = cv2.countNonZero(thresh)
        
        self.previous_frame = frame
        
        if motion_pixels > self.config['motion_threshold']:
            self.motion_detected = True
            self.last_motion_time = datetime.now()
            return True
        else:
            self.motion_detected = False
            return False
    
    def start_motion_detection(self):
        """Démarre la détection de mouvement"""
        self.motion_detection_active = True
        self.motion_thread = threading.Thread(target=self._motion_detection_loop)
        self.motion_thread.daemon = True
        self.motion_thread.start()
        logger.info("Détection de mouvement activée")
    
    def stop_motion_detection(self):
        """Arrête la détection de mouvement"""
        self.motion_detection_active = False
        logger.info("Détection de mouvement désactivée")
    
    def _motion_detection_loop(self):
        """Boucle de détection de mouvement"""
        while self.motion_detection_active:
            try:
                frame = self.picam2.capture_array()
                if self.detect_motion(frame):
                    logger.info("Mouvement détecté!")
                    # Enregistrement automatique en cas de mouvement
                    if not self.is_recording:
                        self.start_recording(60)  # Enregistre 1 minute
                
                time.sleep(0.5)  # Vérifie toutes les 0.5 secondes
                
            except Exception as e:
                logger.error(f"Erreur dans la détection de mouvement: {e}")
                break
    
    def cleanup_old_files(self):
        """Supprime les anciens fichiers"""
        cutoff_date = datetime.now() - timedelta(days=self.config['cleanup_days'])
        
        for directory in [self.config['video_dir'], self.config['photos_dir']]:
            for filename in os.listdir(directory):
                filepath = os.path.join(directory, filename)
                if os.path.isfile(filepath):
                    file_time = datetime.fromtimestamp(os.path.getctime(filepath))
                    if file_time < cutoff_date:
                        os.remove(filepath)
                        logger.info(f"Fichier supprimé: {filename}")
    
    def get_file_list(self):
        """Retourne la liste des fichiers enregistrés"""
        files = {'videos': [], 'photos': []}
        
        # Vidéos
        for filename in os.listdir(self.config['video_dir']):
            filepath = os.path.join(self.config['video_dir'], filename)
            if os.path.isfile(filepath):
                files['videos'].append({
                    'name': filename,
                    'size': os.path.getsize(filepath),
                    'date': datetime.fromtimestamp(os.path.getctime(filepath)).strftime("%Y-%m-%d %H:%M:%S")
                })
        
        # Photos
        for filename in os.listdir(self.config['photos_dir']):
            filepath = os.path.join(self.config['photos_dir'], filename)
            if os.path.isfile(filepath):
                files['photos'].append({
                    'name': filename,
                    'size': os.path.getsize(filepath),
                    'date': datetime.fromtimestamp(os.path.getctime(filepath)).strftime("%Y-%m-%d %H:%M:%S")
                })
        
        return files
    
    def get_status(self):
        """Retourne le statut du système"""
        return {
            'recording': self.is_recording,
            'motion_detection': self.motion_detection_active,
            'motion_detected': self.motion_detected,
            'last_motion': self.last_motion_time.strftime("%Y-%m-%d %H:%M:%S") if self.last_motion_time else None,
            'uptime': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

# Initialisation de l'application Flask
app = Flask(__name__)
camera = SurveillanceCamera()

# Template HTML pour l'interface web
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Surveillance Caméra Pi</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f0f0f0; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }
        .header { text-align: center; margin-bottom: 30px; }
        .video-container { text-align: center; margin: 20px 0; }
        .video-stream { max-width: 100%; border: 2px solid #333; }
        .controls { display: flex; justify-content: center; gap: 10px; margin: 20px 0; flex-wrap: wrap; }
        .btn { padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
        .btn-primary { background: #007bff; color: white; }
        .btn-danger { background: #dc3545; color: white; }
        .btn-success { background: #28a745; color: white; }
        .btn-warning { background: #ffc107; color: black; }
        .status { background: #e9ecef; padding: 15px; border-radius: 5px; margin: 20px 0; }
        .files { margin: 20px 0; }
        .file-list { background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 10px 0; }
        .recording-indicator { color: red; font-weight: bold; }
        .motion-indicator { color: green; font-weight: bold; }
        .text-center { text-align: center; }
        .text-gray-500 { color: var(--color-gray-500); }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏠 Surveillance Caméra Raspberry Pi</h1>
            <p>Interface de contrôle et de surveillance</p>
        </div>
        
        <div class="video-container">
            <img src="{{ url_for('video_feed') }}" class="video-stream" alt="Flux vidéo en direct">
        </div>
        
        <div class="controls">
            <button class="btn btn-danger" onclick="startRecording()">🔴 Démarrer Enregistrement</button>
            <button class="btn btn-primary" onclick="stopRecording()">⏹️ Arrêter Enregistrement</button>
            <button class="btn btn-success" onclick="takePhoto()">📸 Prendre Photo</button>
            <button class="btn btn-warning" onclick="toggleMotionDetection()">👁️ Détection Mouvement</button>
        </div>
        
        <div class="status" id="status">
            <h3>Statut du Système</h3>
            <div id="status-content">Chargement...</div>
        </div>
        
        <div class="files">
            <h3>Fichiers Enregistrés</h3>
            <div id="files-content">Chargement...</div>
        </div>

        <br><p class="text-gray-500 text-center">Créé par Clément JONGHMANS.</p>
    </div>

    <script>
        function updateStatus() {
            fetch('/status')
                .then(response => response.json())
                .then(data => {
                    let html = '<ul>';
                    html += '<li><strong>Enregistrement:</strong> ' + (data.recording ? '<span class="recording-indicator">ACTIF</span>' : 'Inactif') + '</li>';
                    html += '<li><strong>Détection de mouvement:</strong> ' + (data.motion_detection ? '<span class="motion-indicator">ACTIVE</span>' : 'Inactive') + '</li>';
                    html += '<li><strong>Mouvement détecté:</strong> ' + (data.motion_detected ? 'OUI' : 'Non') + '</li>';
                    if (data.last_motion) {
                        html += '<li><strong>Dernier mouvement:</strong> ' + data.last_motion + '</li>';
                    }
                    html += '<li><strong>Système démarré:</strong> ' + data.uptime + '</li>';
                    html += '</ul>';
                    document.getElementById('status-content').innerHTML = html;
                });
        }
        
        function updateFiles() {
            fetch('/files')
                .then(response => response.json())
                .then(data => {
                    let html = '<div class="file-list"><h4>Vidéos (' + data.videos.length + ')</h4><ul>';
                    data.videos.forEach(file => {
                        html += '<li>' + file.name + ' (' + Math.round(file.size/1024/1024) + ' MB) - ' + file.date + '</li>';
                    });
                    html += '</ul></div>';
                    
                    html += '<div class="file-list"><h4>Photos (' + data.photos.length + ')</h4><ul>';
                    data.photos.forEach(file => {
                        html += '<li>' + file.name + ' (' + Math.round(file.size/1024) + ' KB) - ' + file.date + '</li>';
                    });
                    html += '</ul></div>';
                    
                    document.getElementById('files-content').innerHTML = html;
                });
        }
        
        function startRecording() {
            fetch('/start_recording', {method: 'POST'})
                .then(response => response.json())
                .then(data => alert(data.message));
        }
        
        function stopRecording() {
            fetch('/stop_recording', {method: 'POST'})
                .then(response => response.json())
                .then(data => alert(data.message));
        }
        
        function takePhoto() {
            fetch('/take_photo', {method: 'POST'})
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                    updateFiles();
                });
        }
        
        function toggleMotionDetection() {
            fetch('/toggle_motion', {method: 'POST'})
                .then(response => response.json())
                .then(data => alert(data.message));
        }
        
        // Mise à jour automatique toutes les 2 secondes
        setInterval(updateStatus, 2000);
        setInterval(updateFiles, 10000);
        
        // Chargement initial
        updateStatus();
        updateFiles();
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/video_feed')
def video_feed():
    return Response(camera.generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/status')
def status():
    return jsonify(camera.get_status())

@app.route('/files')
def files():
    return jsonify(camera.get_file_list())

@app.route('/start_recording', methods=['POST'])
def start_recording():
    duration = request.json.get('duration', 300) if request.is_json else 300
    success = camera.start_recording(duration)
    return jsonify({
        'success': success,
        'message': 'Enregistrement démarré' if success else 'Erreur lors du démarrage'
    })

@app.route('/stop_recording', methods=['POST'])
def stop_recording():
    success = camera.stop_recording()
    return jsonify({
        'success': success,
        'message': 'Enregistrement arrêté' if success else 'Erreur lors de l\'arrêt'
    })

@app.route('/take_photo', methods=['POST'])
def take_photo():
    filename = camera.take_photo()
    return jsonify({
        'success': filename is not None,
        'message': f'Photo prise: {filename}' if filename else 'Erreur lors de la prise de photo',
        'filename': filename
    })

@app.route('/toggle_motion', methods=['POST'])
def toggle_motion():
    if camera.motion_detection_active:
        camera.stop_motion_detection()
        message = 'Détection de mouvement désactivée'
    else:
        camera.start_motion_detection()
        message = 'Détection de mouvement activée'
    
    return jsonify({
        'success': True,
        'message': message,
        'active': camera.motion_detection_active
    })

def signal_handler(signum, frame):
    """Gestionnaire d'arrêt propre"""
    logger.info(f"Signal {signum} reçu, arrêt en cours...")
    if camera.is_recording:
        camera.stop_recording()
    if camera.motion_detection_active:
        camera.stop_motion_detection()
    if camera.picam2:
        camera.picam2.close()
    os._exit(0)

if __name__ == '__main__':
    import signal
    import sys
    
    # Configuration des gestionnaires de signaux
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Vérification des arguments de ligne de commande
    auto_start = '--auto-start' in sys.argv
    
    try:
        # Nettoyage des anciens fichiers au démarrage
        camera.cleanup_old_files()
        
        # Si mode auto-start, activer automatiquement la détection de mouvement
        if auto_start:
            logger.info("Mode démarrage automatique activé")
            camera.start_motion_detection()
            
            # Créer un fichier de statut pour indiquer que le système est actif
            status_file = f'{os.path.dirname(os.path.abspath(__file__))}/system_active.txt'
            with open(status_file, 'w') as f:
                f.write(f"Système démarré le {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # Démarrage du serveur Flask
        logger.info("Démarrage du serveur de surveillance...")
        logger.info(f"Interface web accessible sur http://[IP_RASPBERRY]:5000")
        logger.info(f"Détection de mouvement: {'ACTIVE' if auto_start else 'INACTIVE'}")
        
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
        
    except KeyboardInterrupt:
        logger.info("Arrêt du système de surveillance (Ctrl+C)")
        signal_handler(signal.SIGINT, None)
    except Exception as e:
        logger.error(f"Erreur fatale: {e}")
        signal_handler(signal.SIGTERM, None)
    finally:
        # Suppression du fichier de statut
        try:
            status_file = f'{os.path.dirname(os.path.abspath(__file__))}/system_active.txt'
            os.remove(status_file)
        except:
            pass
