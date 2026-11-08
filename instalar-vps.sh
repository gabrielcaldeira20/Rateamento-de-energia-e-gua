#!/usr/bin/env bash
# Preparacao inicial de um VPS Ubuntu 22.04 ou 24.04 para rodar o sistema.
# Rode UMA vez, como root, logo depois de criar o servidor:
#     bash instalar-vps.sh
#
# O que ele faz: atualiza o sistema, instala o Docker, liga o firewall,
# cria um usuario comum para o dia a dia e prepara a pasta do projeto.

set -o errexit
set -o nounset

USUARIO="${USUARIO:-alfa}"
PASTA="/opt/alfa-serra-velha"

if [ "$(id -u)" -ne 0 ]; then
    echo "ERRO: rode como root (sudo bash instalar-vps.sh)." >&2
    exit 1
fi

echo "==> 1/6 Atualizando o sistema"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get upgrade -y

echo "==> 2/6 Instalando pacotes de apoio"
apt-get install -y ca-certificates curl git ufw unattended-upgrades

echo "==> 3/6 Instalando o Docker"
if command -v docker >/dev/null 2>&1; then
    echo "    Docker ja esta instalado."
else
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    CODENAME="$(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")"
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${CODENAME} stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker

echo "==> 4/6 Firewall (libera apenas SSH, HTTP e HTTPS)"
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> 5/6 Usuario de trabalho: ${USUARIO}"
if id "$USUARIO" >/dev/null 2>&1; then
    echo "    Usuario ja existe."
else
    adduser --disabled-password --gecos "" "$USUARIO"
    usermod -aG docker "$USUARIO"
    # Copia a sua chave SSH do root para o novo usuario, se existir.
    if [ -f /root/.ssh/authorized_keys ]; then
        mkdir -p "/home/${USUARIO}/.ssh"
        cp /root/.ssh/authorized_keys "/home/${USUARIO}/.ssh/authorized_keys"
        chown -R "${USUARIO}:${USUARIO}" "/home/${USUARIO}/.ssh"
        chmod 700 "/home/${USUARIO}/.ssh"
        chmod 600 "/home/${USUARIO}/.ssh/authorized_keys"
        echo "    Chave SSH copiada para ${USUARIO}."
    else
        echo "    AVISO: nao achei /root/.ssh/authorized_keys."
        echo "    Cadastre a sua chave em /home/${USUARIO}/.ssh/authorized_keys"
        echo "    antes de desligar o login do root."
    fi
fi

echo "==> 6/6 Pasta do projeto"
mkdir -p "${PASTA}/backups"
chown -R "${USUARIO}:${USUARIO}" "$PASTA"

echo
echo "Pronto. Proximos passos:"
echo "  1. Aponte o dominio para o IP deste servidor (registro A)."
echo "  2. Entre como ${USUARIO}:  ssh ${USUARIO}@IP_DO_SERVIDOR"
echo "  3. Clone o projeto em ${PASTA} e copie .env.example para .env."
echo "  4. Preencha o .env e rode:  docker compose up -d --build"
echo
echo "Seguranca: depois de confirmar que entra como ${USUARIO},"
echo "desligue o login direto do root em /etc/ssh/sshd_config"
echo "(PermitRootLogin no e PasswordAuthentication no) e rode: systemctl restart ssh"
