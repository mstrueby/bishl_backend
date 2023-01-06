import { useField } from 'formik';

const InputText = ({ label, ...props }) => {
    const [field, meta] = useField(props);
    const classInputDef = "block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
    const classInputErr = "block w-full rounded-md border-red-300 pr-10 text-red-900 focus:border-red-500 focus:outline-none focus:ring-red-500 sm:text-sm"

console.log("Field name: ", field.name, ", value: ", field.value)

    return (
        <div>
            <label htmlFor={props.id || props.name}
                className="block text-sm font-medium text-gray-700">
                {label}
            </label>
            <div className="relative mt-1 rounded-md shadow-sm">
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
