# RPi-Camera-System_FR

Voici mon guide pour créer un système de surveillance complet avec votre Raspberry Pi Zero 2 W. 
Voici déja le matériel nécessaire :

- [RaspberryPi Zéro 2 W](https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/) (pas WH, sinon il y aura des problèmes avec les broches !)
- [RaspberryPi Camera Module 3 Series](https://www.raspberrypi.com/products/camera-module-3/)
- [Boitier pour Pi Zéro](https://www.raspberrypi.com/products/raspberry-pi-zero-case/) 
- [Alimentation](https://www.raspberrypi.com/products/micro-usb-power-supply/)
- Carte Micro-SD (plus il y a de stockage, mieux ce sera, au minimum 15 Go ; peut importe la marque)

---

Voici un script Python complet et les instructions d'installation.

> N'oubliez pas de remplacer `<VOTRE_NOM_D_UTILISATEUR>` par votre vrai nom d'utilisateur choisi lorsque vous avez installé le système sur RaspberryPi Imager.

## Installation et configuration préliminaire

Installer d'abord RaspberryPi OS Lite (peut-être que d'autres système fonctionnent, je n'ai pas testé) avec [RaspberryPi Imager](https://www.raspberrypi.com/software/).

### 1. Préparation du Raspberry Pi

```bash
# Mise à jour du système
sudo apt update && sudo apt upgrade -y

# Installation des dépendances
sudo apt install python3-pip python3-venv python3-dev git -y

# Activation de la caméra (seulement pour les systèmes anciens, normalement activé par défault)
sudo raspi-config
# Aller dans "Interface Options" > "Camera" > "Enable"

# Redémarrer après activation
sudo reboot

```

### 2. Installation des bibliothèques Python

```bash
# Installation des dépendances libcamera
sudo  apt  install -y python3-libcamera python3-kms++
sudo  apt  install -y python3-prctl libatlas-base-dev ffmpeg python3-pip
sudo  apt  install -y python3-picamera2 --no-install-recommends
```

### 3. Script Python complet

## Instructions d'exécution

### 4. Sauvegarde et exécution du script

```bash
# Créer le dossier du projet
mkdir -p /home/<VOTRE_NOM_D_UTILISATEUR>/surveillance
cd /home/<VOTRE_NOM_D_UTILISATEUR>/surveillance

# Sauvegarder le script (copier le code ci-dessus dans ce fichier)
nano surveillance_camera.py

# Rendre le script exécutable
chmod +x surveillance_camera.py

# Création d'un environnement virtuel avec accès aux paskages système
python3 -m venv --system-site-packages surveillance_env

# Activer l'environnement virtuel
source surveillance_env/bin/activate

# Installez seulement les packages non-système
pip install flask opencv-python-headless numpy pillow

# Lancer le script (avec démarrage automatique)
python3 surveillance_camera.py --auto-start

```

## Fonctionnalités du système

### Interface Web

-   Accès via `http://[IP_DU_RASPBERRY]:5000`
-   Flux vidéo en direct
-   Contrôles d'enregistrement
-   Prise de photos
-   Détection de mouvement

### Fonctions principales

1.  **Streaming en direct** : Flux vidéo accessible via navigateur
2.  **Enregistrement manuel** : Démarrage/arrêt à la demande
3.  **Enregistrement automatique** : En cas de détection de mouvement
4.  **Prise de photos** : Capture d'images haute résolution
5.  **Détection de mouvement** : Surveillance automatique
6.  **Gestion des fichiers** : Nettoyage automatique des anciens fichiers
7.  **Interface web responsive** : Compatible mobile et desktop

### Commandes terminal utiles

```bash
# Vérifier l'état du service
sudo systemctl status surveillance.service

# Voir les logs
sudo journalctl -u surveillance.service -f

# Arrêter le service
sudo systemctl stop surveillance.service

# Redémarrer le service
sudo systemctl restart surveillance.service

# Tester la caméra
libcamera-hello --timeout 5000

```

Le système créera automatiquement les dossiers `/home/<VOTRE_NOM_D_UTILISATEUR>/surveillance/videos` et `/home/<VOTRE_NOM_D_UTILISATEUR>/surveillance/photos` pour stocker les enregistrements. L'interface web sera accessible depuis n'importe quel navigateur sur votre réseau local. Pour voir les photos et vidéos, il faut lire la carte MicroSD dans un lecteur sur une machine Linux et accéder au lecteur rootfs puis sélectionner `/home/<VOTRE_NOM_D_UTILISATEUR>/surveillance/`. Il y aura là les dossiers photos et videos. A l'intérieur de chacun se trouvera les enregistrements sous forme de fichiers MP4 et PNG/JPG.

---

Maintenant, voici comment configurer le système pour qu'il se lance automatiquement au démarrage et s'arrête proprement lors de l'extinction.

## Configuration du démarrage automatique

### 1. Service systemd optimisé

Créez le fichier de service :

```bash
sudo nano /etc/systemd/system/surveillance.service

```

Contenu optimisé pour le démarrage automatique :

```ini
[Unit]
Description=Camera Surveillance System with Auto Motion Detection
After=network.target
Wants=network.target

[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=/home/pi/surveillance
Environment=PATH=/home/pi/surveillance/surveillance_env/bin
Environment=PYTHONPATH=/home/pi/surveillance
ExecStart=/home/pi/surveillance/surveillance_env/bin/python /home/pi/surveillance/surveillance_camera.py --auto-start
ExecStop=/bin/kill -SIGTERM $MAINPID
TimeoutStopSec=30
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target

```

### 2. Configuration et activation du service

```bash
# Installer et configurer le service
sudo systemctl daemon-reload
sudo systemctl enable surveillance.service

# Tester le service
sudo systemctl start surveillance.service
sudo systemctl status surveillance.service

# Voir les logs en temps réel
sudo journalctl -u surveillance.service -f

```

### 3. Script d'arrêt propre pour l'extinction

Créez un script pour l'arrêt propre :

```bash
sudo nano /home/<VOTRE_NOM_D_UTILISATEUR>/surveillance/shutdown_surveillance.sh

```

Contenu :

```bash
#!/bin/bash
# Script d'arrêt propre de la surveillance

echo "Arrêt du système de surveillance..."
sudo systemctl stop surveillance.service

# Attendre que le processus s'arrête complètement
sleep 5

# Vérifier si des processus Python de surveillance sont encore actifs
pkill -f "surveillance_camera.py"

echo "Système de surveillance arrêté"

```

```bash
# Rendre le script exécutable
sudo chmod +x /home/<VOTRE_NOM_D_UTILISATEUR>/surveillance/shutdown_surveillance.sh

```

### 4. Configuration pour l'arrêt automatique lors de l'extinction

Ajoutez le script d'arrêt au processus d'extinction :

```bash
sudo nano /etc/systemd/system/surveillance-shutdown.service

```

Contenu :

```ini
[Unit]
Description=Surveillance Camera Shutdown Service
DefaultDependencies=false
Before=shutdown.target reboot.target halt.target

[Service]
Type=oneshot
RemainAfterExit=true
ExecStart=/bin/true
ExecStop=/home/pi/surveillance/shutdown_surveillance.sh
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target

```

```bash
# Activer le service d'arrêt
sudo systemctl enable surveillance-shutdown.service

```

### 5. Vérification du système automatique

Créez un script de vérification :

```bash
nano /home/<VOTRE_NOM_D_UTILISATEUR>/surveillance/check_system.sh

```

```bash
#!/bin/bash
# Script de vérification du système de surveillance

echo "=== Statut du système de surveillance ==="
echo

# Vérifier si le service est actif
if systemctl is-active --quiet surveillance.service; then
    echo "✅ Service de surveillance : ACTIF"
    echo "🔗 Interface web : http://$(hostname -I | cut -d' ' -f1):5000"
else
    echo "❌ Service de surveillance : INACTIF"
fi

# Vérifier si le fichier de statut existe
if [ -f "/home/pi/surveillance/system_active.txt" ]; then
    echo "✅ Détection de mouvement : ACTIVE"
    cat /home/pi/surveillance/system_active.txt
else
    echo "⚠️  Détection de mouvement : STATUT INCONNU"
fi

# Afficher l'espace disque utilisé
echo
echo "📁 Espace disque utilisé :"
du -sh /home/pi/surveillance/videos/ 2>/dev/null || echo "Aucune vidéo enregistrée"
du -sh /home/pi/surveillance/photos/ 2>/dev/null || echo "Aucune photo prise"

# Afficher les derniers fichiers
echo
echo "📹 Dernières vidéos :"
ls -lt /home/pi/surveillance/videos/ | head -5

echo
echo "📸 Dernières photos :"
ls -lt /home/pi/surveillance/photos/ | head -5

```

```bash
chmod +x /home/<VOTRE_NOM_D_UTILISATEUR>/surveillance/check_system.sh
```

### 6. Commandes utiles pour la gestion

```bash
# Vérifier l'état complet du système
/home/<VOTRE_NOM_D_UTILISATEUR>/surveillance/check_system.sh

# Voir les logs de surveillance
sudo journalctl -u surveillance.service -n 50

# Redémarrer le système de surveillance
sudo systemctl restart surveillance.service

# Arrêter temporairement la surveillance
sudo systemctl stop surveillance.service

# Désactiver le démarrage automatique
sudo systemctl disable surveillance.service

# Réactiver le démarrage automatique
sudo systemctl enable surveillance.service

```

## Fonctionnement automatique

### Au démarrage du Raspberry Pi :

1.  Le service `surveillance.service` se lance automatiquement
2.  La détection de mouvement s'active immédiatement
3.  L'interface web devient accessible sur le port 5000
4.  Le système commence à surveiller et enregistrer automatiquement

### Lors de l'extinction :

1.  Le service `surveillance-shutdown.service` se déclenche
2.  L'enregistrement en cours est terminé proprement
3.  Les ressources sont libérées
4.  Le système s'éteint de manière sécurisée

### Fonctionnalités automatiques :

-   **Enregistrement automatique** lors de la détection de mouvement
-   **Nettoyage automatique** des anciens fichiers (configurable)
-   **Redémarrage automatique** en cas d'erreur
-   **Gestion propre** des ressources système

Votre Raspberry Pi sera maintenant entièrement autonome : branchez-le et il commence automatiquement la surveillance, débranchez-le et il s'arrête proprement !

Pour l'éteindre : `sudo shutdown now`.
