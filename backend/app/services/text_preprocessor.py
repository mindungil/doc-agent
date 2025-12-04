"""
텍스트 전처리 및 정규화 모듈
"""
import re
import unicodedata
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)


class TextPreprocessor:
    """텍스트 전처리 및 정규화"""

    def __init__(self):
        # Kiwi 형태소 분석기 (Lazy initialization)
        self._kiwi = None

    @property
    def kiwi(self):
        """Kiwi 형태소 분석기 (Lazy initialization)"""
        if self._kiwi is None:
            try:
                from kiwipiepy import Kiwi
                self._kiwi = Kiwi()
                logger.info("Kiwi 형태소 분석기 초기화 완료")
            except Exception as e:
                logger.error(f"Kiwi 초기화 실패: {e}")
                self._kiwi = False  # False로 설정하여 재시도 방지
        return self._kiwi if self._kiwi is not False else None

    def clean_title(self, title: str) -> str:
        """제목 정규화 (괄호 패턴 삭제)

        Args:
            title: 원본 제목

        Returns:
            정규화된 제목 (Cleaned Title)

        규칙:
            1. 유니코드 정규화 (NFC)
            2. ( ... ) 및 [ ... ] 패턴 검출
            3. 괄호 내부 문자열 길이가 3글자 이하인 경우 삭제
            4. 4글자 이상인 경우 유의미한 정보로 판단하여 유지
            5. 공백 정규화
        """
        # 1. 유니코드 정규화
        title = unicodedata.normalize('NFC', title)

        # 2. 괄호 패턴 검출 및 처리
        # 소괄호 처리
        title = re.sub(r'\([^)]{1,3}\)', '', title)  # 3글자 이하 삭제
        # 대괄호 처리
        title = re.sub(r'\[[^\]]{1,3}\]', '', title)  # 3글자 이하 삭제

        # 3. 공백 정규화
        title = re.sub(r'\s+', ' ', title)  # 연속 공백을 단일 공백으로
        title = title.strip()  # 앞뒤 공백 제거

        return title

    def extract_nouns(self, text: str) -> List[str]:
        """명사 추출 (BM25S 검색용)

        Args:
            text: 입력 텍스트

        Returns:
            명사 리스트
        """
        try:
            # Kiwi로 명사 추출 (사용 가능한 경우)
            if self.kiwi is not None:
                # Kiwi 분석 수행
                result = self.kiwi.analyze(text)

                nouns = []
                for token in result[0][0]:
                    # 명사 태그: NNG(일반명사), NNP(고유명사), NNB(의존명사)
                    if token[1] in ['NNG', 'NNP', 'NNB']:
                        word = token[0]
                        # 1글자 명사 제거 (조사 등)
                        if len(word) > 1:
                            nouns.append(word)

                return nouns
            else:
                # Kiwi를 사용할 수 없을 때 fallback: 공백 기반 토크나이징
                logger.warning("Kiwi를 사용할 수 없어 fallback 토크나이징 사용")
                return [w for w in text.split() if len(w) > 1]
        except Exception as e:
            # 실패 시 공백 기반 토크나이징
            logger.error(f"명사 추출 실패: {e}, fallback 사용")
            return [w for w in text.split() if len(w) > 1]

    def tokenize(self, text: str) -> List[str]:
        """토크나이징 (형태소 분석)

        Args:
            text: 입력 텍스트

        Returns:
            토큰 리스트
        """
        # 정규화
        text = self.clean_title(text)
        # 명사 추출
        return self.extract_nouns(text)

    def extract_bracket_content(self, title: str) -> Tuple[str, List[str], List[str]]:
        """괄호 내용 추출 (분석용)

        Args:
            title: 원본 제목

        Returns:
            (정규화된 제목, 소괄호 내용 리스트, 대괄호 내용 리스트)
        """
        title = unicodedata.normalize('NFC', title)

        # 소괄호 내용 추출
        round_brackets = re.findall(r'\(([^)]+)\)', title)

        # 대괄호 내용 추출
        square_brackets = re.findall(r'\[([^\]]+)\]', title)

        # 정규화된 제목
        cleaned = self.clean_title(title)

        return cleaned, round_brackets, square_brackets


# 싱글톤 인스턴스
_preprocessor = None


def get_preprocessor() -> TextPreprocessor:
    """전처리기 싱글톤 인스턴스 반환"""
    global _preprocessor
    if _preprocessor is None:
        _preprocessor = TextPreprocessor()
    return _preprocessor
