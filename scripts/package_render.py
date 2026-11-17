"""Create a small, explicit deployment bundle without local credentials/results."""
from pathlib import Path
import hashlib
import json
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]


def main():
    names=[
        'render.yaml', '.python-version', '.gitignore', 'requirements-render.txt',
        'requirements.txt', 'pyproject.toml', 'app.py', 'run.py', 'README.md',
        '.streamlit/config.toml', 'Matriz_15_productos_actualizada (1) (1).xlsx',
        'docs/DESPLIEGUE_RENDER.md', 'docs/MANUAL_USUARIO.md',
        'scripts/render-build.sh', 'scripts/check_render.py', 'scripts/package_render.py',
    ]
    paths=[ROOT/name for name in names]
    paths+=sorted((ROOT/'src/sqv').glob('*.py'))
    paths+=sorted((ROOT/'assets').glob('*.css'))
    paths+=sorted((ROOT/'configs').glob('*.yaml'))
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f'Falta un archivo del paquete: {path.relative_to(ROOT)}')
    checksums={}
    target=ROOT/'SQV_Render.zip'
    with ZipFile(target,'w',ZIP_DEFLATED) as archive:
        for path in paths:
            name=path.relative_to(ROOT).as_posix()
            content=path.read_bytes()
            archive.writestr(name,content)
            checksums[name]=hashlib.sha256(content).hexdigest()
        archive.writestr('MANIFIESTO_PAQUETE.json',json.dumps({
            'source':'Matriz_15_productos_actualizada (1) (1).xlsx',
            'sha256':checksums},indent=2,ensure_ascii=False))
    print(f'Paquete: {target.name} · {len(paths)} archivos · {target.stat().st_size:,} bytes')


if __name__=='__main__':
    main()
