import { useState, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { documentApi } from '../api/client'

interface DocumentUploadProps {
  onUploadSuccess?: () => void
}

interface UploadProgress {
  filename: string
  status: 'pending' | 'uploading' | 'success' | 'error'
  error?: string
}

export default function DocumentUpload({ onUploadSuccess }: DocumentUploadProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [uploadQueue, setUploadQueue] = useState<UploadProgress[]>([])
  const [isUploading, setIsUploading] = useState(false)
  const queryClient = useQueryClient()

  const processUploads = useCallback(async (files: File[]) => {
    setIsUploading(true)
    const progressList: UploadProgress[] = files.map(f => ({
      filename: f.name,
      status: 'pending',
    }))
    setUploadQueue(progressList)

    // 동기 처리: 한 파일씩 순차적으로 업로드
    for (let i = 0; i < files.length; i++) {
      const file = files[i]
      setUploadQueue(prev => 
        prev.map((item, idx) => 
          idx === i ? { ...item, status: 'uploading' } : item
        )
      )

      try {
        await documentApi.uploadDocument(file)
        setUploadQueue(prev => 
          prev.map((item, idx) => 
            idx === i ? { ...item, status: 'success' } : item
          )
        )
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : '알 수 없는 오류'
        setUploadQueue(prev => 
          prev.map((item, idx) => 
            idx === i ? { ...item, status: 'error', error: errorMessage } : item
          )
        )
      }
    }

    setIsUploading(false)
    queryClient.invalidateQueries({ queryKey: ['documents'] })
    onUploadSuccess?.()

    // 3초 후 진행 상황 초기화
    setTimeout(() => {
      setUploadQueue([])
    }, 3000)
  }, [queryClient, onUploadSuccess])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)

      const files = Array.from(e.dataTransfer.files).filter(
        f => f.type === 'application/pdf' || 
             f.name.endsWith('.docx') || 
             f.name.endsWith('.doc') || 
             f.name.endsWith('.txt')
      )
      
      if (files.length > 0) {
        await processUploads(files)
      }
    },
    [processUploads]
  )

  const handleFileSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files
      if (files && files.length > 0) {
        const fileArray = Array.from(files).filter(
          f => f.type === 'application/pdf' || 
               f.name.endsWith('.docx') || 
               f.name.endsWith('.doc') || 
               f.name.endsWith('.txt')
        )
        await processUploads(fileArray)
        // input 초기화
        e.target.value = ''
      }
    },
    [processUploads]
  )

  return (
    <div className="space-y-4">
      <div
        className={`border-4 border-dashed rounded-2xl p-12 text-center transition-all ${
          isDragging
            ? 'border-white bg-blue-800 scale-[1.02]'
            : 'border-blue-300 bg-white hover:border-white hover:bg-blue-800'
        } ${isUploading ? 'opacity-50 pointer-events-none' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <div className="mb-6">
          <svg
            className={`mx-auto h-24 w-24 ${isDragging ? 'text-white' : 'text-blue-600'}`}
            stroke="currentColor"
            fill="none"
            viewBox="0 0 48 48"
          >
            <path
              d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
              strokeWidth={2.5}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        <p className={`text-2xl font-bold mb-3 ${isDragging ? 'text-white' : 'text-gray-800'}`}>
          {isDragging ? '여기에 파일을 놓으세요' : '파일을 드래그 앤 드롭'}
        </p>
        <p className={`text-base mb-8 ${isDragging ? 'text-blue-100' : 'text-gray-600'}`}>
          또는 아래 버튼을 클릭하여 파일을 선택하세요 (PDF, DOCX, TXT)
        </p>
        <label className="inline-block">
          <span className="inline-flex items-center gap-3 px-12 py-6 bg-white text-blue-700 border-2 border-blue-300 rounded-2xl cursor-pointer hover:bg-blue-50 hover:border-blue-500 shadow-xl hover:shadow-2xl transition-all font-bold text-xl">
            <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            파일 선택하기
          </span>
          <input
            type="file"
            className="hidden"
            accept=".pdf,.docx,.doc,.txt"
            multiple
            onChange={handleFileSelect}
            disabled={isUploading}
          />
        </label>
      </div>

      {uploadQueue.length > 0 && (
        <div className="bg-white rounded-xl shadow-md p-4 border border-gray-200">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">업로드 진행 상황</h3>
          <div className="space-y-2">
            {uploadQueue.map((item, idx) => (
              <div key={idx} className="flex items-center justify-between p-2 bg-gray-50 rounded-lg">
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <div className="flex-shrink-0">
                    {item.status === 'pending' && (
                      <div className="w-5 h-5 border-2 border-gray-300 border-t-blue-600 rounded-full animate-spin"></div>
                    )}
                    {item.status === 'uploading' && (
                      <div className="w-5 h-5 border-2 border-gray-300 border-t-blue-600 rounded-full animate-spin"></div>
                    )}
                    {item.status === 'success' && (
                      <svg className="w-5 h-5 text-green-600" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                      </svg>
                    )}
                    {item.status === 'error' && (
                      <svg className="w-5 h-5 text-red-600" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                      </svg>
                    )}
                  </div>
                  <span className="text-sm text-gray-700 truncate flex-1">{item.filename}</span>
                </div>
                <div className="flex-shrink-0 ml-2">
                  {item.status === 'pending' && (
                    <span className="text-xs text-gray-500">대기 중</span>
                  )}
                  {item.status === 'uploading' && (
                    <span className="text-xs text-blue-600 font-medium">업로드 중...</span>
                  )}
                  {item.status === 'success' && (
                    <span className="text-xs text-green-600 font-medium">완료</span>
                  )}
                  {item.status === 'error' && (
                    <span className="text-xs text-red-600 font-medium">실패</span>
                  )}
                </div>
              </div>
            ))}
          </div>
          {uploadQueue.some(item => item.error) && (
            <div className="mt-3 p-2 bg-red-50 border border-red-200 rounded-lg">
              {uploadQueue
                .filter(item => item.error)
                .map((item, idx) => (
                  <p key={idx} className="text-xs text-red-700">
                    {item.filename}: {item.error}
                  </p>
                ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

