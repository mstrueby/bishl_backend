import { NavLink } from 'react-router-dom'

function classNames(...classes) {
    return classes.filter(Boolean).join(' ')
}

const Sidebar = (props) => {
    let navigation = props.navigation

    return (
                <aside className='py-6 md:col-span-3'>
                    <nav className="space-y-1 bg-white" aria-label="Sidebar">
                        {navigation.map((item) => (
                            <NavLink
                                key={item.name}
                                to={item.href}
                                className={({ isActive }) => classNames(isActive
                                    ? 'bg-indigo-50 border-indigo-600 text-indigo-600 group flex items-center px-3 py-2 text-sm font-medium border-l-4'
                                    : 'border-transparent text-gray-600 hover:bg-gray-50 hover:text-gray-900 group flex items-center px-3 py-2 text-sm font-medium border-l-4'
                                )}
                            >
                                <item.icon
                                    // activeClassName='text-indigo-500' -- ungelöst
                                    className='text-gray-400 group-hover:text-gray-500 mr-3 flex-shrink-0 h-6 w-6'
                                    aria-hidden="true"
                                />
                                {item.name}
                            </NavLink>
                        ))}
                    </nav>
                </aside>
    )
}

export default Sidebar