import Layout from "./Layout"
import LmSidebar from "../admin/components/LmSidebar"

const Backend = ({ sidebar, content }) => {
    return (
        <div className="relative">
            <div className="mx-auto max-w-screen-xl pb-6 lg:pb-16">
                <div className="overflow-hidden bg-white">
                    <div className="divide-y divide-gray-200 md:grid md:grid-cols-12 md:divide-y-0 md:divide-x">
                        {sidebar}
                        <main className="px-4 md:px-8 py-6 md:col-span-9">
                            {content}
                        </main>
                    </div>
                </div>
            </div>
        </div>
    )
}

export default Backend