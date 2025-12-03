"""직급 매핑 서비스 (Hybrid 매핑)"""
import re
from typing import Optional


class RankMapper:
    """
    직급/직위 → 숫자 레벨 변환

    행정 시스템의 더러운 데이터(Dirty Data)를 처리:
    - "7급" (숫자 급수)
    - "지방행정주사보" (직급명)
    - "주무관" (직위명)
    """

    # 급수 기반 매핑 (숫자가 클수록 하위 직급)
    GRADE_MAP = {
        "1급": 1, "2급": 2, "3급": 3, "4급": 4, "5급": 5,
        "6급": 6, "7급": 7, "8급": 8, "9급": 9,
    }

    # 직급명 기반 매핑 (지방직 기준)
    TITLE_MAP = {
        # 고위공무원
        "고위공무원": 1,

        # 일반직 (지방)
        "지방부이사관": 2,
        "지방이사관": 3,
        "지방서기관": 4,
        "지방행정사무관": 5, "지방시설사무관": 5, "지방농업사무관": 5,
        "지방행정주사": 6, "지방시설주사": 6, "지방농업주사": 6,
        "지방행정주사보": 7, "지방시설주사보": 7, "지방농업주사보": 7,
        "지방행정서기": 8, "지방시설서기": 8, "지方농업서기": 8,
        "지방행정서기보": 9, "지방시설서기보": 9, "지방농업서기보": 9,

        # 연구직
        "연구관": 5,
        "연구사": 6,
        "연구원": 7,

        # 기능직
        "기능8급": 8, "기능9급": 9,
    }

    # 직위명 기반 매핑 (실무 호칭)
    POSITION_MAP = {
        # 관리직
        "실장": 2, "국장": 3, "과장": 4, "팀장": 5,

        # 실무직
        "사무관": 5,
        "주무관": 7, "주사": 6, "주사보": 7,
        "서기": 8, "서기보": 9,
    }

    @classmethod
    def get_rank_level(cls, rank_str: str) -> int:
        """
        직급/직위 문자열을 숫자 레벨로 변환

        Args:
            rank_str: 직급 문자열 (예: "7급", "주무관", "지방행정주사보")

        Returns:
            int: 직급 레벨 (1=최고위, 9=최하위)
                 매핑 실패 시 7 반환 (일반 주무관 수준)
        """
        if not rank_str:
            return 7  # 기본값: 주무관

        rank_str = rank_str.strip()

        # 1. 급수 패턴 매칭 (예: "7급")
        grade_match = re.search(r'(\d)급', rank_str)
        if grade_match:
            grade = int(grade_match.group(1))
            return cls.GRADE_MAP.get(f"{grade}급", 7)

        # 2. 직급명 완전 일치
        if rank_str in cls.TITLE_MAP:
            return cls.TITLE_MAP[rank_str]

        # 3. 직위명 부분 일치 (예: "정책주무관" → "주무관")
        for position_key, level in cls.POSITION_MAP.items():
            if position_key in rank_str:
                return level

        # 4. 매핑 실패 시 기본값
        return 7  # 일반 실무자로 간주

    @classmethod
    def is_working_level(cls, rank_str: str, threshold: int = 7) -> bool:
        """
        실무자(Working Level) 여부 판단

        Args:
            rank_str: 직급 문자열
            threshold: 실무자 기준 (기본값 7 = 7급 이하)

        Returns:
            bool: 실무자이면 True
        """
        level = cls.get_rank_level(rank_str)
        return level >= threshold

    @classmethod
    def compare_ranks(cls, rank_a: str, rank_b: str) -> int:
        """
        두 직급 비교

        Args:
            rank_a: 직급 A
            rank_b: 직급 B

        Returns:
            int: -1 (A가 상위), 0 (동일), 1 (B가 상위)
        """
        level_a = cls.get_rank_level(rank_a)
        level_b = cls.get_rank_level(rank_b)

        if level_a < level_b:
            return -1
        elif level_a > level_b:
            return 1
        else:
            return 0


# 싱글톤 인스턴스
rank_mapper = RankMapper()
