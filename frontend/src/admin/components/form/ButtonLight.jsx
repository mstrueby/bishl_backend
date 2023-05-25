import { useField } from 'formik';

const ButtonLight = ({ children, ...props }) => {
    const [field, meta] = useField(props);

    return (
        <button
            {...field} {...props}
            className="inline-flex justify-center rounded-md border border-gray-300 bg-white py-2 px-4 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:ring-offset-2"
        >{children}</button>
    )
}

export default ButtonLight;