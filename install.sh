#!/bin/bash

# Set the minor version of Python3
PYTHON_MINOR_VERSION=9
VIRTUALENV_NAME=env-3.${PYTHON_MINOR_VERSION}
USER=pi

# Check if the specified Python version is installed
if ! python3.${PYTHON_MINOR_VERSION} --version &>/dev/null; then
    read -p "Python 3.${PYTHON_MINOR_VERSION} is not installed. Do you want to install it? (y/n): " choice
    if [[ "$choice" == [Yy]* ]]; then
        echo "Adding deadsnakes PPA and installing Python 3.${PYTHON_MINOR_VERSION}."
        sudo add-apt-repository ppa:deadsnakes/ppa
        sudo apt-get update
        sudo apt-get install -y python3.${PYTHON_MINOR_VERSION}
    else
        echo "Installation aborted. Define desired Python Version in installation script."
        exit 1
    fi
else
    echo "Using Python 3.${PYTHON_MINOR_VERSION}"
    sudo apt-get update
fi

# Install required packages for the specified minor version
sudo apt-get install -y python3.${PYTHON_MINOR_VERSION}-pip python3-venv python3.${PYTHON_MINOR_VERSION}-distutils

# Create a virtual environment
python3.${PYTHON_MINOR_VERSION} -m venv ${VIRTUALENV_NAME}

# Activate the virtual environment
source ${VIRTUALENV_NAME}/bin/activate

# for arm architectures, add piwheels.org pip extra-index-url
if [[ "$(uname -m)" == "arm"* || "$(uname -m)" == "aarch64" ]]; then
    read -p "Detected ARM platform. Do you want to add piwheels.org extra-index-url to pip configuration? (y/n): " choice
    if [[ "$choice" == [Yy]* ]]; then
        echo "Adding extra-index-url to pip configuration."
        mkdir -p ~/.pip
        echo "[global]" > ~/.pip/pip.conf
        echo "extra-index-url=https://www.piwheels.org/simple" >> ~/.pip/pip.conf
    else
        echo "Skipping extra-index-url configuration."
    fi
fi

# Install the required packages from requirements.txt
python3.${PYTHON_MINOR_VERSION} -m pip install -r requirements.txt
# Hint: in case using armv7l (arm 32-bit) there is no pyarrow binary available which is required for streamlit
# In this case, you need to build pyarrow by yourself

# sudo apt install libtiff5-dev # required for PIL/matplotlib
sudo apt install libnss3-dev # required for Plotly

# configure systemctrl services
# pv-logger.service
read -p "Do you want to create and configure the pv-logger.service? (y/n): " choice
if [[ "$choice" == [Yy]* ]]; then
    
    sudo bash -c 'cat <<EOF > /etc/systemd/system/pv-logger.service
[Unit]
Description=PV logger daemon

[Service]
WorkingDirectory=/home/${PYTHON_MINOR_VERSION}/pv-dashboard/
User=${PYTHON_MINOR_VERSION}
ExecStart=/home/${PYTHON_MINOR_VERSION}/pv-dashboard/env-3.${PYTHON_MINOR_VERSION}/bin/python3 logger/logger.py
Type=simple

[Install]
WantedBy=multi-user.target
EOF'

    # Reload systemd to apply the new service
    sudo systemctl daemon-reload

    # Enable the service to start on boot
    sudo systemctl enable pv-logger.service

    # Start the service
    sudo systemctl start pv-logger.service
else
    echo "Skipping pv-logger.service configuration."
fi

# pv-bot.service
read -p "Do you want to create and configure the pv-bot.service? (y/n): " choice
if [[ "$choice" == [Yy]* ]]; then
    
    sudo bash -c 'cat <<EOF > /etc/systemd/system/pv-bot.service
[Unit]
Description=PV bot daemon

[Service]
WorkingDirectory=/home/${PYTHON_MINOR_VERSION}/pv-dashboard/
User=${PYTHON_MINOR_VERSION}
Environment=PYTHONPATH=/home/${PYTHON_MINOR_VERSION}/pv-dashboard/
ExecStart=/home/${PYTHON_MINOR_VERSION}/pv-dashboard/env-3.${PYTHON_MINOR_VERSION}/bin/python3 bot/bot.py
Type=simple

[Install]
WantedBy=multi-user.target
EOF'

    # Reload systemd to apply the new service
    sudo systemctl daemon-reload

    # Enable the service to start on boot
    sudo systemctl enable pv-bot.service

    # Start the service
    sudo systemctl start pv-bot.service
else
    echo "Skipping pv-bot.service configuration."
fi

# pv-dashboard.service
read -p "Do you want to create and configure the pv-dashboard.service? (y/n): " choice
if [[ "$choice" == [Yy]* ]]; then
    
    sudo bash -c 'cat <<EOF > /etc/systemd/system/pv-dashboard.service
[Unit]
Description=PV dashboard daemon

[Service]
WorkingDirectory=/home/${PYTHON_MINOR_VERSION}/pv-dashboard/
User=${PYTHON_MINOR_VERSION}
Environment=PYTHONPATH=/home/${PYTHON_MINOR_VERSION}/pv-dashboard/
ExecStart=/home/${PYTHON_MINOR_VERSION}/pv-dashboard/env-3.${PYTHON_MINOR_VERSION}/bin/python3 dashboard/dashboard.py
Type=simple

[Install]
WantedBy=multi-user.target
EOF'

    # Reload systemd to apply the new service
    sudo systemctl daemon-reload

    # Enable the service to start on boot
    sudo systemctl enable pv-dashboard.service

    # Start the service
    sudo systemctl start pv-dashboard.service
else
    echo "Skipping pv-dashboard.service configuration."
fi
