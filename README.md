# SK hynix DART Financial Dashboard

🔗 대시보드 바로가기: https://hsc-class02.github.io/SB_SKhynix/

SK hynix 정기보고서(사업·반기·분기)의 재무데이터를 OpenDART API로 수집하고 재무비율을 계산해 GitHub Pages로 시각화하는 프로젝트입니다.

## 핵심 기능
- 2010년부터 사업·반기·분기보고서 수집
- 2015년 이후 OpenDART XBRL 재무제표 API 사용
- 2010~2014년 DART 공시검색 + 원문 XML legacy 추출
- Annual / Half-year / Quarterly 표
- 매출·영업이익·순이익 및 영업이익률·ROE·ROA 등 figures
- 국내 peer firms 표
- 매월 1일 GitHub Actions 자동 업데이트 및 Pages 배포

## OpenDART API Key
GitHub `Settings → Secrets and variables → Actions → New repository secret`에서:

`OPENDART_API_KEY = 발급받은 40자리 인증키`

API key는 코드에 직접 입력하지 않습니다.

## 국내 Peer Firms
| 기업 | 구분 | 종목코드 | 비고 |
|---|---|---:|---|
| 삼성전자 | 국내 상장 | 005930 | 메모리·시스템반도체 등 |
| DB하이텍 | 국내 상장 | 000990 | 파운드리 |
| 한미반도체 | 국내 상장 | 042700 | 반도체 후공정 장비 |
| LX세미콘 | 국내 상장 | 108320 | 반도체 설계 |
| SK실트론 | 국내 기업 | - | 반도체 웨이퍼 |

Peer는 동일 사업을 의미하는 순위가 아니라 산업·공급망 관점의 참고 목록입니다.

## 주의
OpenDART의 정형 재무제표 API는 2015년 이후 사업연도를 제공합니다. 2010~2014년은 원문 parser를 사용하며 계정명 차이로 일부 값이 비어 있을 수 있습니다.
