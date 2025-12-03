import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { documentApi } from '../api/client'

interface RecommendationProgressProps {
  documentId: number
  onComplete?: () => void
}

export default function RecommendationProgress({ documentId, onComplete }: RecommendationProgressProps) {
  const [currentStep, setCurrentStep] = useState<string>('')

  const { data: document } = useQuery({
    queryKey: ['document', documentId],
    queryFn: () => documentApi.getDocument(documentId),
    enabled: !!documentId,
    refetchInterval: (query) => {
      const doc = query.state.data
      if (!doc) return false
      
      // 추천 완료되면 폴링 중지
      if (doc.status === '담당자 추천 완료' || doc.status === '배부 완료' || doc.status === '오류') {
        if (onComplete && doc.status === '담당자 추천 완료') {
          onComplete()
        }
        return false
      }
      
      // 진행 중이면 2초마다 폴링
      return 2000
    },
  })

  useEffect(() => {
    if (document) {
      setCurrentStep(document.status)
    }
  }, [document])

  const getStepInfo = (status: string) => {
    switch (status) {
      case '대기':
        return { label: '대기 중', progress: 0, color: 'bg-gray-400' }
      case 'RAG 분석 중':
        return { label: 'RAG 분석 중...', progress: 33, color: 'bg-blue-500' }
      case 'LLM 분석 중':
        return { label: 'LLM 분석 중...', progress: 66, color: 'bg-blue-600' }
      case '담당자 추천 완료':
        return { label: '추천 완료', progress: 100, color: 'bg-green-500' }
      case '오류':
        return { label: '오류 발생', progress: 0, color: 'bg-red-500' }
      default:
        return { label: status, progress: 0, color: 'bg-gray-400' }
    }
  }

  const stepInfo = getStepInfo(currentStep)

  if (!currentStep || currentStep === '담당자 추천 완료' || currentStep === '배부 완료' || currentStep === '오류') {
    return null
  }

  return (
    <div className="bg-white rounded-lg shadow-md p-6 mb-6">
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-gray-900 mb-2">담당자 추천 진행 상황</h3>
        <p className="text-sm text-gray-600">{stepInfo.label}</p>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-2.5">
        <div
          className={`${stepInfo.color} h-2.5 rounded-full transition-all duration-500`}
          style={{ width: `${stepInfo.progress}%` }}
        ></div>
      </div>
      <div className="mt-4 flex justify-between text-xs text-gray-500">
        <span>1. RAG 분석</span>
        <span>2. LLM 분석</span>
        <span>3. 추천 완료</span>
      </div>
    </div>
  )
}

