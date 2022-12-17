import Layout from "./Layout"
import LmSidebar from "../admin/components/LmSidebar"

const AdmLayout = ({ children }) => {
    return (
        // <div className="mx-auto max-w-7xl sm:px-6 lg:px-8 ">
        <div className="">
            {/* <Header /> */}
            <Layout>
                <main className="relative">
                    <div className="mx-auto max-w-screen-xl pb-6 lg:pb-16">
                        <div className="overflow-hidden bg-white">
                            <div className="divide-y divide-gray-200 md:grid md:grid-cols-12 md:divide-y-0 md:divide-x">
                                <LmSidebar />
                                <div className="px-4 md:px-8 py-6 md:col-span-9">
                                    {children}
                                </div>
                            </div>
                        </div>
                    </div>
                </main>
            </Layout>
        </div>
    )
}

export default AdmLayout