# Э������֤

���ֿ�����������úͿ�ֿ�Э��˵�����ȴ����� `main` �������ܷ�֧������޸ĺ��� `main` �ύ Pull Request��������鼰 CI ͨ����ϲ����׶γɹ�ͨ�����ֿ� `main` �� `release` �� Pull Request ���ܡ��������ʵƾ�ݻ����������ύ�� Git��

## ��ǰ���÷�Χ

��ǰ `docker-compose.yml` ���Ǿ� Docker ģ�壺Core API ʹ�� SQLite�������˿�Ϊ 5000��Web �����˿�Ϊ 3000���������� R25 PostgreSQL �������з�ʽ��ͬ��`.env.example` �еľ�����Ŀ¼Ҳֻ��ģ�����ã����ܾݴ��жϵ�ǰ��������ʵ�ʰ汾��·����

���� CI ֻ��� Shell �﷨�� Compose �����ܷ���ȷ�������ϲ���������ȡ���񡢲�����������Ҳ����ִ�� `scripts/start.sh`��`scripts/stop.sh` ���л� R25 ��������`release` �ϲ�ĿǰҲ���ᴥ�����ֿ����������R25 ��ͨ���������������Ҫ��� [Э��˵��](docs/collaboration.md)��������֤ͨ����������������ͨ����

## �ύ����

1. ���±��� `main`���½� `feat/`��`fix/`��`docs/` �� `codex/` ��֧��
2. һ�� PR ����һ����ȷ���⡣��ֿ�Ķ�Ӧ�������й������� PR����ע������˳��
3. ʹ��ʾ�������ļ�ִ������������֤��ֻ������֤�����ִ��������ֹͣ�ű���
4. �� PR ģ����дʵ����֤��������� `main` �ύ��
5. �ɸ�������ˣ�CI ͨ����ϲ�����Ҫ�����׶γɹ�ʱ�������ύ `main` �� `release` �� PR��

## ������֤

��Ҫ Bash��Docker CLI ��֧�� GPU `gpus` �ֶε� Docker Compose �����`config --quiet` ֻ��֤���ã�����Ҫ���� Docker �����������������֤�����ļ��� GPU �ϲ�����ļ���ȱ�� Compose ʱӦ�Ȱ�װ�����ܰ���������ͨ����

```bash
set -Eeuo pipefail
while IFS= read -r -d '' script; do
  bash -n "$script"
done < <(find scripts -type f -name '*.sh' -print0)

temporary_dir="$(mktemp -d)"
trap 'rm -f "$temporary_dir/.env"; rmdir "$temporary_dir"' EXIT
cp .env.example "$temporary_dir/.env"
docker compose --env-file "$temporary_dir/.env" \
  -f docker-compose.yml config --quiet
docker compose --env-file "$temporary_dir/.env" \
  -f docker-compose.yml -f docker-compose.gpu.yml config --quiet
```

����ʹ�õ���ʾ��ֵ����ʱ�ļ����˳�ʱɾ����CI ����ȡ���������ļ���Ҳ�����չ����Ļ�������ֵ���ֿ�ԭ�� `scripts/validate.sh` �ڹ���ȱʧʱ�����������ּ�飬��˱��� CI ֱ�ӵ�������ǿ�Ƽ�顣

## �ֿ������Ҫ��������

`CODEOWNERS` ָ�� `@Hang-666-star` Ϊ�����ˣ����ļ���������ǿ����ˡ��ֿ����Ա�������� main/release �� PR ��˹���Code Owner ��˺ͱ���״̬��顣���� `main` Ҫ�� `Validate deployment configuration`��`release` ��ҪҪ�� `Verify main-to-release promotion`����ֱֹ�����͡�ǿ�����ͺ�ɾ����������֧������Ա�ƹ������������Ҫ�������������ܵ�����ʵ�ֵġ������� PR ���󡱡�
