# KSE Custom Agents

KSE 프로젝트 전용 Claude Code 에이전트 설정 파일입니다.

## 설치

Claude Code에서 사용하려면 `.claude/agents/`에 복사:

```bash
# Linux / macOS
mkdir -p .claude/agents
cp docs/agents/kse-*.md .claude/agents/

# Windows
mkdir .claude\agents
copy docs\agents\kse-*.md .claude\agents\
```

## 에이전트 목록

| 에이전트 | 역할 | 트리거 키워드 |
|----------|------|---------------|
| **kse-dev** | 기능 개발 | "새 기능 추가", "exporter 만들어", "파이프라인 수정" |
| **kse-test** | 테스트 실행 + 분석 | "테스트 돌려", "실패 원인", "검증해" |
| **kse-build** | 빌드 + 배포 + CI/CD | "빌드해", "릴리스", "CI 수정", "패키징" |
| **kse-review** | 코드 품질 리뷰 | "코드 리뷰", "품질 검사", "이상한 데 없나" |
| **kse-mesh** | 메시/FEA 전문 | "TetGen 오류", ".k 파일", "메시 품질", "비다양체" |
| **kse-doc** | 문서 작성 + 유지 | "문서 업데이트", "README 수정", "API 문서" |

## 사용법

Claude Code에서 자동으로 에이전트를 인식합니다:

```
사용자: "단위 테스트 전부 돌려봐"
→ kse-test 에이전트가 자동 할당

사용자: "새로운 Nastran exporter 추가해"
→ kse-dev 에이전트가 자동 할당

사용자: "체적 메시에서 TetGen segfault 나는데"
→ kse-mesh 에이전트가 자동 할당
```

## 에이전트 워크플로우

```
기능 요청
  │
  ├─→ kse-dev      구현
  │
  ├─→ kse-test     테스트 실행
  │
  ├─→ kse-review   코드 리뷰
  │
  ├─→ kse-mesh     메시 문제 전문 처리
  │
  ├─→ kse-doc      문서 반영
  │
  └─→ kse-build    빌드 + 배포
```
