# SK hynix DART Financial Dashboard

[![🔗 대시보드 바로가기](https://img.shields.io/badge/%F0%9F%94%97-%EB%8C%80%EC%8B%9C%EB%B3%B4%EB%93%9C%20%EB%B0%94%EB%A1%9C%EA%B0%80%EA%B8%B0-0b57d0?style=for-the-badge)](https://hsc-class02.github.io/SB_SKhynix/)

SK hynix의 DART 정기보고서(사업·반기·분기)를 OpenDART API로 수집하고, 주요 재무수치와 재무비율을 계산하여 GitHub Pages 대시보드로 제공하는 자동화 프로젝트입니다.

## Dashboard

**[🔗 SK hynix Financial Dashboard](https://hsc-class02.github.io/SB_SKhynix/)**

- 2010년부터 사업보고서·반기보고서·분기보고서 수집
- 2015년 이후: OpenDART XBRL 재무제표 API를 사업연도 기준으로 직접 조회
- 2010~2014년: DART 원문 XML 기반 legacy parser
- Annual / Half-year / Quarterly 데이터 테이블
- 매출액·영업이익·당기순이익·자산·부채·자본·현금흐름 등 주요 지표
- 영업이익률·순이익률·ROE·ROA·부채비율·유동비율·총자산회전율
- 국내 peer firms 표
- 매월 1일 GitHub Actions 자동 업데이트 및 GitHub Pages 재배포

## Automatic update

Workflow: .github/workflows/update-and-deploy.yml

- Schedule: 매월 1일 00:15 UTC = 한국시간 09:15
- Manual run: GitHub → Actions → Update DART data and deploy dashboard → Run workflow
- 수집 → 분석 → data/ 갱신 → docs/index.html 생성 → GitHub Pages 배포 순서로 실행합니다.

## OpenDART API Key

GitHub에서 다음 위치에 등록합니다.

Settings → Secrets and variables → Actions → New repository secret

Secret 이름: OPENDART_API_KEY

API key는 소스 코드에 저장하지 않고 GitHub Actions Secret으로만 전달합니다.

## 주요 데이터 구조

| 구분 | 내용 |
|---|---|
| Annual | 사업보고서 |
| Half-year | 반기보고서 |
| Quarterly | 1분기·3분기보고서 |
| Coverage | 2010–현재 |
| Source | OpenDART |
| Dashboard | GitHub Pages |

## 국내 Peer Firms

| 기업 | 구분 | 종목코드 | 비고 |
|---|---|---:|---|
| 삼성전자 | 국내 상장 | 005930 | 메모리·시스템반도체 |
| DB하이텍 | 국내 상장 | 000990 | 파운드리 |
| 한미반도체 | 국내 상장 | 042700 | 반도체 후공정 장비 |
| LX세미콘 | 국내 상장 | 108320 | 반도체 설계 |
| SK실트론 | 국내 기업 | - | 반도체 웨이퍼 |

> Peer는 동일한 사업모델을 의미하는 순위가 아니라 국내 반도체 산업·공급망 관점의 참고 기업 목록입니다.

## Data quality notes

- DART의 접수연도와 사업연도는 서로 다를 수 있으므로, 2015년 이후 데이터는 bsns_year를 기준으로 조회하도록 구성했습니다. 특히 사업보고서가 다음 해에 제출되는 문제를 피합니다.
- 2010~2014년은 정형 XBRL API가 아닌 원문 문서 parser를 사용하므로 일부 계정은 누락될 수 있습니다.
- 정정공시가 제출되면 공시 데이터가 변경될 수 있으므로 중요한 분석에서는 DART 원문을 함께 확인해야 합니다.
