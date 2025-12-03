import type { EmployeeCandidate } from '../types'

interface AssigneeCardProps {
  employee: EmployeeCandidate
  isPrimary?: boolean
  reasoning?: string
}

export default function AssigneeCard({ employee, isPrimary = false, reasoning }: AssigneeCardProps) {
  const deptParts = [employee.dept1]
  if (employee.dept2) deptParts.push(employee.dept2)
  if (employee.dept3) deptParts.push(employee.dept3)
  const deptStr = deptParts.join(' ')

  return (
    <div
      className={`bg-white rounded-lg shadow-md p-6 ${
        isPrimary ? 'border-2 border-blue-500' : ''
      }`}
    >
      {isPrimary && (
        <div className="mb-4">
          <span className="px-3 py-1 bg-blue-600 text-white rounded-full text-sm font-medium">
            1순위 추천
          </span>
        </div>
      )}
      <div className="space-y-3">
        <div>
          <h3 className="text-xl font-bold text-gray-900">{employee.name}</h3>
          <p className="text-gray-600 text-sm mt-0.5">{employee.rank}</p>
        </div>
        <div className="flex items-center gap-2">
          <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          <p className="text-gray-700 font-medium text-sm">{deptStr}</p>
        </div>
        <div className="pt-2 border-t border-gray-200">
          <p className="text-sm text-gray-600 mb-1">
            <span className="font-medium">업무:</span> {employee.tasks}
          </p>
          {employee.phone && (
            <p className="text-sm text-gray-600">
              <span className="font-medium">내선번호:</span> {employee.phone}
            </p>
          )}
          {employee.score && (
            <p className="text-xs text-gray-500 mt-2">
              <span className="font-medium">유사도 점수:</span> {employee.score.toFixed(4)}
            </p>
          )}
        </div>
        {reasoning && (
          <div className="mt-4 p-4 bg-gradient-to-br from-blue-50 to-indigo-50 rounded-lg border border-blue-200">
            <div className="flex items-start gap-2">
              <svg className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
              </svg>
              <div className="flex-1">
                <p className="text-xs font-semibold text-blue-900 mb-1">LLM 추천 근거</p>
                <p className="text-sm text-gray-800 leading-relaxed">{reasoning}</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

