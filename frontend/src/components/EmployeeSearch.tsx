import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { documentApi } from '../api/client'
import type { EmployeeCandidate } from '../types'

interface EmployeeSearchProps {
  onSelect: (employee: EmployeeCandidate) => void
  excludeNames?: string[]
}

export default function EmployeeSearch({ onSelect, excludeNames = [] }: EmployeeSearchProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [isOpen, setIsOpen] = useState(false)

  const { data: employees, isLoading } = useQuery({
    queryKey: ['employee-search', searchQuery],
    queryFn: () => documentApi.searchEmployees(searchQuery, 10),
    enabled: searchQuery.length >= 2 && isOpen,
  })

  const filteredEmployees = employees?.filter(
    (emp) => !excludeNames.includes(emp.name)
  ) || []

  const handleSelect = (employee: EmployeeCandidate) => {
    onSelect(employee)
    setIsOpen(false)
    setSearchQuery('')
  }

  return (
    <div className="relative">
      <div className="flex gap-2">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => {
            setSearchQuery(e.target.value)
            setIsOpen(true)
          }}
          onFocus={() => setIsOpen(true)}
          placeholder="직원 검색 (이름, 부서, 업무 등)"
          className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
        {isOpen && (
          <button
            onClick={() => setIsOpen(false)}
            className="px-4 py-2 text-gray-600 hover:text-gray-800"
          >
            취소
          </button>
        )}
      </div>

      {isOpen && searchQuery.length >= 2 && (
        <div className="absolute z-10 w-full mt-2 bg-white border border-gray-300 rounded-lg shadow-lg max-h-96 overflow-y-auto">
          {isLoading ? (
            <div className="p-4 text-center text-gray-500">검색 중...</div>
          ) : filteredEmployees.length === 0 ? (
            <div className="p-4 text-center text-gray-500">검색 결과가 없습니다.</div>
          ) : (
            <ul className="divide-y divide-gray-200">
              {filteredEmployees.map((employee, idx) => {
                const deptParts = [employee.dept1]
                if (employee.dept2) deptParts.push(employee.dept2)
                if (employee.dept3) deptParts.push(employee.dept3)
                const deptStr = deptParts.join(' ')

                return (
                  <li
                    key={idx}
                    onClick={() => handleSelect(employee)}
                    className="p-4 hover:bg-gray-50 cursor-pointer transition-colors"
                  >
                    <div className="flex justify-between items-start">
                      <div>
                        <p className="font-semibold text-gray-900">{employee.name}</p>
                        <p className="text-sm text-gray-600">{employee.rank}</p>
                        <p className="text-sm text-gray-500">{deptStr}</p>
                        <p className="text-xs text-gray-400 mt-1">{employee.tasks}</p>
                      </div>
                      {employee.phone && (
                        <span className="text-xs text-gray-500">{employee.phone}</span>
                      )}
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

