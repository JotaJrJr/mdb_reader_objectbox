# MDB Reader

Leitor desktop para arquivos `.mdb` — suporta bancos Microsoft Access (Jet/ACE) e bancos gerados pelo **ObjectBox Flutter ORM** (formato LMDB + FlatBuffers).

---

## Funcionalidades

- Abre arquivos `.mdb` via drag-and-drop ou menu File
- Navega tabelas na sidebar com contagem de linhas
- Editor SQL com execução via `F5`
- Resultados paginados (500 linhas/página) com cópia de linha como JSON
- Suporte a bancos ObjectBox Flutter com leitura via `objectbox-model.json`
- Diagnóstico de erros com mensagens e passos de solução

---

## Requisitos

### Python
```
Python 3.12+
```

### Dependências
```bash
pip install -r requirements.txt
```

### ACE ODBC Driver (obrigatório para arquivos Access padrão)

O driver **não** é instalado automaticamente — precisa ser instalado manualmente no sistema.

1. Verifique o bitness do seu Python:
   ```bash
   python -c "import struct; print(struct.calcsize('P')*8)"
   ```
2. Baixe o driver correspondente em:  
   https://www.microsoft.com/en-us/download/details.aspx?id=54920
   - `accessdatabaseengine.exe` → 32-bit
   - `accessdatabaseengine_X64.exe` → 64-bit
3. Instale e reinicie o app

> **Arquivos ObjectBox** não precisam do ACE driver — são lidos diretamente.

---

## Como rodar

```bash
python main.py
```

---

## Abrindo um banco ObjectBox Flutter

Bancos gerados pelo ObjectBox Flutter ORM usam formato proprietário (LMDB + FlatBuffers). O app detecta automaticamente. Para ver os campos corretamente:

1. Abra o arquivo `.mdb` normalmente
2. Vá em **File → Load ObjectBox schema…**
3. Selecione o arquivo `objectbox-model.json` do seu projeto Flutter

---

## Desenvolvimento

### Rodar testes
```bash
pytest -q
```

### Instalar pre-commit hook (bloqueia commit se testes falharem)
```bash
pip install pre-commit
pre-commit install
```

---

## Stack

| Camada | Tecnologia |
|---|---|
| UI | PyQt6 |
| Acesso MDB (primário) | pyodbc + ACE ODBC Driver |
| Acesso MDB (fallback) | ADODB via pywin32 |
| Formato ObjectBox | Parser LMDB + FlatBuffers próprio |
| Testes | pytest + pytest-qt |
| Empacotamento | PyInstaller |
