# 설치 안내

1. 저장소 루트에 ZIP 내용을 복사합니다.
2. GitHub `Settings → Secrets and variables → Actions → New repository secret`에서 `OPENDART_API_KEY`를 등록합니다.
3. `GITHUB_WORKFLOW/update-and-deploy.yml`을 `.github/workflows/update-and-deploy.yml`로 복사합니다.
4. GitHub `Settings → Pages → Source`를 `GitHub Actions`로 설정합니다.
5. Actions에서 `Update DART data and deploy dashboard`를 수동 실행합니다.
6. 매월 1일 UTC 00:15(한국시간 09:15)에 자동 실행됩니다.

## About 링크
저장소 우측 `About → Edit`에서 Website에 다음을 입력합니다.

`https://hsc-class02.github.io/SB_SKhynix/`

## README 배지
사용자가 제공한 배지 이미지를 `docs/assets/dashboard-badge.png`로 올린 뒤 다음을 README 최상단에 사용할 수 있습니다.

`[![🔗 대시보드 바로가기](docs/assets/dashboard-badge.png)](https://hsc-class02.github.io/SB_SKhynix/)`

## API Key는 코드에 넣지 않습니다
OpenDART 인증키는 GitHub Actions Secret으로만 전달됩니다.
