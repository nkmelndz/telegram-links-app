
import csv
import json
import os
import re
from src.services.telegram_service import TelegramService
from src.scrapers import SCRAPERS



DOMAIN_TO_PLATFORM = {
    'linkedin.com': 'LinkedIn',
    'dev.to': 'Dev.to',
    'youtube.com': 'YouTube',
    'youtu.be': 'YouTube',
    'medium.com': 'Medium',
    'instagram.com': 'Instagram',
    'tiktok.com': 'TikTok',
}

def pick_scraper(url: str):
    for domain, platform in DOMAIN_TO_PLATFORM.items():
        if domain in url:
            fn = SCRAPERS.get(platform)
            if fn:
                return platform, fn
    return None, None

def run(args):
    
    # Read config
    if not os.path.exists("config.json"):
        print("❌ Config file not found. Run 'telelinker setup' first.")
        return
    with open("config.json", "r") as f:
        cfg = json.load(f)
    api_id = cfg["API_ID"]
    api_hash = cfg["API_HASH"]
    session_name = cfg["SESSION_NAME"]

    session_file = f"{session_name}.session"
    if not os.path.exists(session_file):
        print(f"❌ Session not found. Run 'telelinker login' to authenticate.")
        return
    
    limit = getattr(args, "limit", None)
    formato = args.format
    groups = []
    if getattr(args, "groups_file", None):
        # Read groups from file
        with open(args.groups_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    # Allow format: id,name
                    parts = line.split(",")
                    group_id = parts[0].strip()
                    groups.append(group_id)
    else:
        groups = [args.group]

    tg_service = TelegramService(session_name, api_id, api_hash)

    out_file = getattr(args, "out", None) or ("posts.csv" if formato=="csv" else "posts.sql")
    fieldnames = ["group_id","autor_contenido","likes","comentarios","compartidos","visitas","fecha_publicacion","tipo_contenido"]
    total_posts = 0
    if formato == "csv":
        with open(out_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for group in groups:
                if limit is not None:
                    print(f"📡 Fetching up to {limit} posts from group {group}...")
                else:
                    print(f"📡 Fetching all posts from group {group}...")
                for i, msg in enumerate(tg_service.iter_group_messages(int(group))):
                    if limit is not None and i >= int(limit):
                        break
                    if not msg.message:
                        continue
                    urls = re.findall(r'(https?://[^\s]+)', msg.message)
                    for url in urls:
                        plataforma, fn = pick_scraper(url)
                        if not fn:
                            continue
                        datos = fn(url)
                        datos['url'] = url
                        datos['plataforma'] = plataforma
                        if all(datos.get(k) is not None for k in ('autor_contenido','likes','comentarios','fecha_publicacion')):
                            row = {
                                'autor_contenido': datos['autor_contenido'],
                                'likes': datos['likes'],
                                'comentarios': datos['comentarios'],
                                'compartidos': datos.get('compartidos', None),
                                'visitas': datos.get('visitas', None),
                                'fecha_publicacion': datos['fecha_publicacion'],
                                'tipo_contenido': datos.get('tipo_contenido', None),
                                'group_id': group
                            }
                            writer.writerow(row)
                            total_posts += 1
                            print(f"\nLink inserted: {datos['url']} ({datos['plataforma']})")
        tg_service.disconnect()
        print(f"✅ Export complete: {total_posts} posts saved to {out_file}")
    elif formato == "postgresql":
        create_table_stmt = (
            "CREATE TABLE posts (\n"
            "    id SERIAL PRIMARY KEY,\n"
            "    url TEXT NOT NULL,\n"
            "    platform VARCHAR(50) NOT NULL,\n"
            "    content_type VARCHAR(50),\n"
            "    author VARCHAR(100),\n"
            "    date TIMESTAMP,\n"
            "    likes INT,\n"
            "    comments INT,\n"
            "    shared INT,\n"
            "    visit INT\n"
            ");\n\n"
        )
        file_exists = os.path.exists(out_file)
        with open(out_file, "w" if not file_exists else "a", encoding="utf-8") as f:
            if not file_exists:
                f.write(create_table_stmt)
            table_name = "posts"
            for group in groups:
                if limit is not None:
                    print(f"📡 Fetching up to {limit} posts from group {group}...")
                else:
                    print(f"📡 Fetching all posts from group {group}...")
                for i, msg in enumerate(tg_service.iter_group_messages(int(group))):
                    if limit is not None and i >= int(limit):
                        break
                    if not msg.message:
                        continue
                    urls = re.findall(r'(https?://[^\s]+)', msg.message)
                    for url in urls:
                        plataforma, fn = pick_scraper(url)
                        if not fn:
                            continue
                        datos = fn(url)
                        datos['url'] = url
                        datos['plataforma'] = plataforma
                        if all(datos.get(k) is not None for k in ('autor_contenido','likes','comentarios','fecha_publicacion')):
                            # Mapear los datos al formato de la tabla
                            def sql_str(val):
                                if val is None:
                                    return "NULL"
                                if isinstance(val, str):
                                    return "'{}'".format(val.replace("'", "''"))
                                return str(val)

                            values = [
                                sql_str(datos.get('url')),
                                sql_str(datos.get('plataforma')),
                                sql_str(datos.get('tipo_contenido')),
                                sql_str(datos.get('autor_contenido')),
                                sql_str(datos.get('fecha_publicacion')),
                                sql_str(datos.get('likes')),
                                sql_str(datos.get('comentarios')),
                                sql_str(datos.get('compartidos')),
                                sql_str(datos.get('visitas'))
                            ]
                            f.write(f"INSERT INTO {table_name} (url, platform, content_type, author, date, likes, comments, shared, visit) VALUES ({', '.join(values)});\n")
                            total_posts += 1
                            print(f"\nLink inserted: {datos['url']} ({datos['plataforma']})")
        tg_service.disconnect()
        print(f"✅ Export complete: {total_posts} posts saved to {out_file} (PostgreSQL)")
    else:
        tg_service.disconnect()
        print("Format not supported.")