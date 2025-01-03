import os
import subprocess
import shutil
from minio import Minio
from minio.error import S3Error
from utils import green, logger
import moviepy.editor as mp
from datetime import datetime

current_datetime = datetime.now()
currentAction = current_datetime.strftime("%d-%m-%Y--%H-%M-%S")

# Inicializa o cliente MinIO com variáveis de ambiente
def initialize_minio_client():
    MINIO_URL = os.environ['MINIO_URL']
    MINIO_PORT = os.environ['MINIO_PORT']
    MINIO_ROOT_USER = os.environ['MINIO_ROOT_USER']
    MINIO_ROOT_PASSWORD = os.environ['MINIO_ROOT_PASSWORD']

    return Minio(
        f"{MINIO_URL}:{MINIO_PORT}",
        access_key=MINIO_ROOT_USER,
        secret_key=MINIO_ROOT_PASSWORD,
        secure=False,
    )

# Verifica se o arquivo tem extensão .mp3
def verificar_extensao_arquivo_mp3(caminho_arquivo):
    _, extensao = os.path.splitext(caminho_arquivo)
    return extensao.lower() == ".mp3"

# Cria um diretório, caso ele não exista
def create_directory(path):
    try:
        os.makedirs(path)
        logger.debug(green(f"Diretório {path} criado com sucesso!"))
    except FileExistsError:
        logger.debug(green(f"Diretório {path} já existe."))

# Faz upload de arquivos para o bucket
def postFileInBucket(client, bucket_name, path_dest, path_src, content_type=None):
    if path_src.endswith('.txt'):
        content_type = 'text/plain'
    logger.debug(green(f"Fazendo upload no bucket {bucket_name}, arquivo {path_dest}"))
    client.fput_object(
        bucket_name,
        path_dest,
        path_src,
        content_type=content_type
    )
    logger.debug(green(f"Upload do arquivo {path_src} realizado com sucesso."))

# Baixa o primeiro arquivo MP3 encontrado apenas na raiz do bucket
def download_mp3_from_bucket(client, bucket_name):
    objects = client.list_objects(bucket_name, prefix="", recursive=False)
    for obj in objects:
        logger.debug(green(f"Download: {obj.object_name}"))
        if verificar_extensao_arquivo_mp3(obj.object_name) and '/' not in obj.object_name:
            local_filename = obj.object_name.replace('\\', '/').split('/')[-1]
            client.fget_object(bucket_name, obj.object_name, f"/app/foredit/{local_filename}")
            logger.debug(green(f"{local_filename} Download realizado com sucesso."))
            return local_filename
    return None

# Processa o arquivo de áudio e vídeo (edição, conversão e upload para o bucket)
def process_audio_video(nameProcessedFile, client, bucketSet):
    # Cria diretório para arquivos editados
    pathDirFilesEdited = "/app/edited/"
    create_directory(pathDirFilesEdited)

    # Edita o vídeo para remover silêncios
    margin = os.getenv("AUTO_EDITOR_MARGIN", "0.04sec")
    subprocess.run([
        "auto-editor", 
        f"./foredit/{nameProcessedFile}",
        "--margin", margin,
        "-o", f"{pathDirFilesEdited}WithoutSilence-{nameProcessedFile}"
    ])
    logger.debug(green(f"Editado: {nameProcessedFile}"))

    # Reconverte MP4 para MP3
    clip = mp.AudioFileClip(f"{pathDirFilesEdited}WithoutSilence-{nameProcessedFile}")
    clip.write_audiofile(f"{pathDirFilesEdited}{nameProcessedFile}")

    # Faz upload do arquivo processado para o bucket
    postFileInBucket(client, bucketSet, f"files-without-silence/{nameProcessedFile}", f"{pathDirFilesEdited}{nameProcessedFile}", 'audio/mpeg')

    # Remove os diretórios temporários usados para edição
    shutil.rmtree(pathDirFilesEdited)
    shutil.rmtree("/app/foredit/")

    # Remove o arquivo original do bucket após o processamento
    client.remove_object(bucketSet, f"{nameProcessedFile}")
    logger.debug(green(f"Arquivo original removido do bucket: {nameProcessedFile}"))

# Função principal
def main():
    bucketSet = "autoeditor"
    client = initialize_minio_client()

    logger.debug(green(f'...START -> {currentAction}'))

    # Tenta baixar o primeiro arquivo MP3 do bucket
    nameProcessedFile = download_mp3_from_bucket(client, bucketSet)

    if nameProcessedFile:
        # Processa o arquivo se encontrado
        process_audio_video(nameProcessedFile, client, bucketSet)
    else:
        logger.debug(green(f"Nenhum arquivo MP3 encontrado no bucket {bucketSet}"))

    logger.debug(green('...FINISHED...'))

if __name__ == "__main__":
    try:
        main()
    except S3Error as exc:
        logger.debug(green("Erro ocorrido: ", exc))
