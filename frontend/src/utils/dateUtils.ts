/**
 * 날짜/시간 유틸리티 함수
 * 서버에서 UTC로 저장된 시간을 한국 시간(KST, UTC+9)으로 변환
 */

/**
 * UTC 시간 문자열을 한국 시간으로 변환하여 포맷팅
 * @param dateString UTC 시간 문자열 (ISO 8601 형식)
 * @param format 포맷 옵션 ('full' | 'date' | 'time' | 'short')
 * @returns 포맷된 한국 시간 문자열
 */
export function formatToKST(
  dateString: string | null | undefined,
  format: 'full' | 'date' | 'time' | 'short' = 'full'
): string {
  if (!dateString) return '-'
  
  try {
    const date = new Date(dateString)
    
    // Intl.DateTimeFormat을 사용하여 한국 시간으로 변환
    const formatter = new Intl.DateTimeFormat('ko-KR', {
      timeZone: 'Asia/Seoul',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    })
    
    const parts = formatter.formatToParts(date)
    const year = parts.find(p => p.type === 'year')?.value || ''
    const month = parts.find(p => p.type === 'month')?.value || ''
    const day = parts.find(p => p.type === 'day')?.value || ''
    const hours = parts.find(p => p.type === 'hour')?.value || ''
    const minutes = parts.find(p => p.type === 'minute')?.value || ''
    const seconds = parts.find(p => p.type === 'second')?.value || ''
    
    switch (format) {
      case 'date':
        return `${year}-${month}-${day}`
      case 'time':
        return `${hours}:${minutes}:${seconds}`
      case 'short':
        return `${month}/${day} ${hours}:${minutes}`
      case 'full':
      default:
        return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
    }
  } catch (error) {
    console.error('날짜 포맷팅 오류:', error)
    return '-'
  }
}

/**
 * 한국 시간으로 변환하여 toLocaleString 사용
 * @param dateString UTC 시간 문자열
 * @returns 한국 시간으로 포맷된 문자열
 */
export function formatToKSTLocale(dateString: string | null | undefined): string {
  if (!dateString) return '-'
  
  try {
    const date = new Date(dateString)
    
    // timeZone 옵션을 사용하여 한국 시간으로 자동 변환
    return date.toLocaleString('ko-KR', {
      timeZone: 'Asia/Seoul',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    })
  } catch (error) {
    console.error('날짜 포맷팅 오류:', error)
    return '-'
  }
}

/**
 * 짧은 형식으로 한국 시간 표시 (MM/DD HH:mm)
 * @param dateString UTC 시간 문자열
 * @returns 포맷된 문자열
 */
export function formatToKSTShort(dateString: string | null | undefined): string {
  if (!dateString) return '-'
  
  try {
    const date = new Date(dateString)
    
    // Intl.DateTimeFormat을 사용하여 한국 시간으로 변환
    const formatter = new Intl.DateTimeFormat('ko-KR', {
      timeZone: 'Asia/Seoul',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    })
    
    const parts = formatter.formatToParts(date)
    const month = parts.find(p => p.type === 'month')?.value || ''
    const day = parts.find(p => p.type === 'day')?.value || ''
    const hours = parts.find(p => p.type === 'hour')?.value || ''
    const minutes = parts.find(p => p.type === 'minute')?.value || ''
    
    return `${month}/${day} ${hours}:${minutes}`
  } catch (error) {
    console.error('날짜 포맷팅 오류:', error)
    return '-'
  }
}

