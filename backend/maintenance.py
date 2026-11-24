"""Offline maintenance: backup, restore to a NEW folder, grant an admin role."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tempfile
import zipfile


@contextmanager
def connection(path):
    conn=sqlite3.connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()


def check_db(path):
    with connection(path) as conn:
        if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('数据库完整性校验失败')
        if conn.execute('PRAGMA foreign_key_check').fetchone(): raise ValueError('数据库关联校验失败')
        tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'users','courses','materials'}<=tables: raise ValueError('不是过了么数据库')


def backup(db_path,output):
    db_path=Path(db_path).resolve();output=Path(output).resolve()
    if not db_path.is_file(): raise ValueError('数据库不存在')
    if output.exists(): raise ValueError('输出文件已存在，请使用新的备份文件名')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        folder=Path(temp);snapshot=folder/'app.db'
        with connection(db_path) as source,connection(snapshot) as target: source.backup(target)
        with connection(snapshot) as conn: conn.execute('DELETE FROM sessions')
        check_db(snapshot)
        files={'app.db':snapshot}
        with connection(snapshot) as conn:
            for mid,suffix in conn.execute('SELECT id,suffix FROM materials'):
                filename=mid+suffix
                if Path(filename).name!=filename or '/' in filename or '\\' in filename: raise ValueError('资料文件名无效')
                p=db_path.parent/'uploads'/filename
                if not p.is_file() or p.is_symlink(): raise ValueError('原始资料缺失，备份未生成：'+filename)
                files['uploads/'+filename]=p
        manifest={name:digest(p) for name,p in files.items()}
        archive=folder/'backup.zip'
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for name,p in files.items(): z.write(p,name)
            z.writestr('manifest.json',json.dumps({'format':1,'files':manifest}))
        # Exclusive create protects existing backups, even after concurrent checks.
        with output.open('xb') as dest,archive.open('rb') as source: shutil.copyfileobj(source,dest)
    return output


def restore(archive,destination):
    destination=Path(destination).resolve()
    if destination.exists(): raise ValueError('恢复目录必须不存在，禁止覆盖当前数据')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temp:
        folder=Path(temp)/'restored';folder.mkdir()
        with zipfile.ZipFile(archive) as z:
            names=z.namelist()
            if len(names)!=len(set(names)) or len(names)>100000: raise ValueError('备份条目重复或过多')
            if sum(i.file_size for i in z.infolist())>10*1024**3: raise ValueError('备份超过10GB恢复上限')
            if 'manifest.json' not in names or z.getinfo('manifest.json').file_size>10*1024**2: raise ValueError('备份清单无效')
            manifest=json.loads(z.read('manifest.json'))
            if not isinstance(manifest,dict) or manifest.get('format')!=1 or not isinstance(manifest.get('files'),dict): raise ValueError('备份清单无效')
            if set(names)!={'manifest.json',*manifest['files']} or 'app.db' not in manifest['files']: raise ValueError('备份清单不匹配')
            for name,expected in manifest['files'].items():
                parts=PurePosixPath(name).parts
                if name!='app.db' and (len(parts)!=2 or parts[0]!='uploads'): raise ValueError('备份路径无效')
                if '\\' in name or ':' in name or '..' in parts or name.startswith('/'): raise ValueError('备份路径无效')
                p=folder.joinpath(*parts);p.parent.mkdir(exist_ok=True)
                with z.open(name) as source,p.open('xb') as target: shutil.copyfileobj(source,target)
                if digest(p)!=expected: raise ValueError('备份校验失败：'+name)
        check_db(folder/'app.db')
        with connection(folder/'app.db') as conn:
            for mid,suffix in conn.execute('SELECT id,suffix FROM materials'):
                filename=mid+suffix
                if '/' in filename or '\\' in filename or ':' in filename or not (folder/'uploads'/filename).is_file(): raise ValueError('备份缺少原始资料或资料路径无效')
            conn.execute('DELETE FROM sessions')
        folder.rename(destination)
    return destination


def main():
    parser=argparse.ArgumentParser(description='过了么离线维护；操作前请停止服务。备份包含所有账号的学习数据，不含API密钥。')
    sub=parser.add_subparsers(dest='command',required=True)
    b=sub.add_parser('backup');b.add_argument('--db',default='data/app.db');b.add_argument('--output',required=True)
    r=sub.add_parser('restore');r.add_argument('--archive',required=True);r.add_argument('--destination',required=True)
    a=sub.add_parser('grant-admin');a.add_argument('--db',default='data/app.db');a.add_argument('--username',required=True)
    args=parser.parse_args()
    try:
        if args.command=='backup': print(backup(args.db,args.output))
        elif args.command=='restore': print(restore(args.archive,args.destination))
        else:
            path=Path(args.db)
            if not path.is_file(): raise ValueError('数据库不存在')
            with connection(path) as conn:
                if not conn.execute("UPDATE users SET role='admin',active=1 WHERE username=?",(args.username,)).rowcount: raise ValueError('请先在网页注册该用户')
            print('已授予管理员权限，请重新登录')
    except (ValueError,OSError,sqlite3.Error,zipfile.BadZipFile,KeyError) as e: parser.exit(1,str(e)+'\n')


if __name__=='__main__': main()
