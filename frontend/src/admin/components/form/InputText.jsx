import { useField } from 'formik';

const InputText = ({ label, ...props }) => {
    const [field, meta] = useField(props);
    const classInputDef = "mt-1 block w-full rounded-md py-2 px-3 border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
    const classInputErr = "mt-1 block w-full rounded-md py-2 px-3 border-red-300 pr-10 text-red-900 focus:border-red-500 focus:outline-none focus:ring-red-500 sm:text-sm"

    return (
        <div className="mt-6 grid grid-cols-12 gap-6">
            <div className="col-span-12 sm:col-span-6">
                <label htmlFor={props.id || props.name}
                    className="block text-sm font-medium text-gray-700">
                    {label}
                </label>
                <input
                    className={meta.touched && meta.error ? classInputErr : classInputDef}
                    {...field} {...props}
                />
                {meta.touched && meta.error ? (
                    <p className="mt-2 text-sm text-red-600">
                        {meta.error}
                    </p>
                ) : null}
            </div>
        </div>
    )
};

export default InputText;
